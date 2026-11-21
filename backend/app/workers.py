import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from .ai.classify_reply import classify_reply, ReplyAnalysis
from .ai.draft_escalation import draft_escalation
from .ai.draft_complaint import prepare_email, validate_draft
from .config import get_settings
from .demo.clock import now
from .engine.company import load_companies
from .engine.policy import decide, Decision
from .engine.sector import effective_sector
from .mail.imap_poll import poll
from .mail.smtp_send import send_email
from .models import Case, CaseStatus, Deadline, Evidence, Event, Level, Message
from .engine.send_guard import guard

logger=logging.getLogger(__name__)

def worker_failure(app, worker: str, error: Exception) -> bool:
    config=get_settings()
    safe=str(error)
    for secret in (config.openai_api_key.get_secret_value(),config.user_email_app_password.get_secret_value(),config.demo_company_app_password.get_secret_value()):
        if secret: safe=safe.replace(secret,'[REDACTED]')
    errors=getattr(app.state,'worker_errors',{})
    count=errors.get(worker,{}).get('count',0)+1
    errors[worker]={'count':count,'error':type(error).__name__+': '+safe}
    app.state.worker_errors=errors
    import json
    logger.error(json.dumps({'worker':worker,**errors[worker]}))
    return count>=2


_write_lock = asyncio.Lock()
_send_lock = asyncio.Lock()


async def act(app, case_id: str, analysis: ReplyAnalysis | None = None, breached: bool = False, redress_breached: bool = False, promise_expired: bool = False) -> None:
    config=app.state.config
    from .ai.sample_detection import ensure_sample_scan
    await ensure_sample_scan(app.state.engine,case_id)
    with Session(app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case or case.status==CaseStatus.RESOLVED or case.facts_json.get('verification_paused') or case.facts_json.get('paused'): return
        messages=session.exec(select(Message).where(Message.case_id==case.id).order_by(Message.sent_at)).all()
        level_messages=[m for m in messages if m.level==case.level]
        deflections=sum(m.classification_json.get('category')=='deflection' for m in level_messages if m.direction=='in')
        outbound=sum(m.direction=='out' for m in messages)
        followups=max(0,sum(m.direction=='out' for m in level_messages)-1)
        limit=config.grievance_followup_limit if case.level==Level.L2 else config.nodal_followup_limit
        clock=now(session) if case.facts_json.get('demo_sample') and config.demo_mode else datetime.now(timezone.utc)
        deadline=(clock+timedelta(days=2)).date().isoformat()
        from .api.profile import get_profile
        profile=get_profile(session,config.user_email)
    company=next((c for c in load_companies() if c['id']==case.company_id),None)
    decision=decide(case.level.value,analysis.category if analysis else 'acknowledged',deflections,breached,analysis.offered_amount_inr if analysis else None,case.amount_inr,bool(case.facts_json.get('missing_info')),sector=effective_sector(company,case.facts_json),followups=followups,followup_limit=limit,redress_breached=redress_breached,bounced=bool(case.facts_json.get('recipient_bounced')),outbound_count=outbound,outbound_limit=config.max_outbound_per_case)
    promise=case.facts_json.get('promise')
    if promise and decision.action in ('wait','followup','escalate','confirm_receipt') and not redress_breached and not breached:
        grace=datetime.fromisoformat(promise['grace_until'])
        if promise.get('exceeds_redress') and not promise.get('pushback_sent') and not (analysis and analysis.refund_confirmed):
            decision=Decision('followup',case.level.value,f"Promise exceeds the redressal deadline {promise['redress_date']}: {promise['quote']}")
        elif clock<grace and decision.action!='confirm_receipt':
            decision=Decision('wait',case.level.value,f"Waiting for the promised date {promise['promised_date']} plus one day of grace.",False)
        elif promise_expired and not promise.get('exceeds_redress'):
            decision=Decision('followup',case.level.value,f"Promise passed on {promise['promised_date']}: {promise['quote']}")
    event=Event(case_id=case.id,actor='ai',type='decision',title=decision.action,reason=decision.reason,payload_json={'action':decision.action,'level':decision.level,'requires_approval':decision.requires_approval})
    draft=None;outgoing=None;status=case.status;new_level=Level(decision.level)
    if decision.action=='confirm_receipt': status=CaseStatus.AWAITING_RECEIPT
    elif decision.action in ('ask_user','user_review','offer_choice'): status=CaseStatus.NEEDS_INFO
    elif decision.action in ('followup','escalate','counter','reply_info','prepare_filing'):
        try:
            draft=await draft_escalation(case.facts_json,[{'date':m.sent_at.date().isoformat(),'body':m.body_text} for m in messages],decision.reason,deadline)
        except Exception:
            if decision.action!='prepare_filing': raise
            from .ai.draft_complaint import EmailDraft
            draft=EmailDraft(subject='Consumer complaint',body=f"Issue: {case.facts_json.get('issue_summary_en') or case.title}\nRequested remedy: {case.demand or 'Needs user review'}\nPlease review the case evidence and correspondence.",cited_refs=[],attachments=[],demand=case.demand or '',deadline_date=deadline)
        draft=prepare_email(draft,case.facts_json,profile,company);validate_draft(draft,deadline)
        if promise and decision.action=='followup' and (promise_expired or promise.get('exceeds_redress')):
            note=f"Your reply stated: “{promise['quote']}” (promised date: {promise['promised_date']})."
            if promise.get('exceeds_redress'):
                note+=f" Please address this by the redressal deadline of {promise['redress_date']}."
            draft=draft.model_copy(update={'body':draft.body.replace('\n\nSincerely,',f'\n\n{note}\n\nSincerely,')})
            validate_draft(draft,deadline)
        contact=(company or {}).get('nodal_officer' if new_level==Level.L3 else 'grievance_officer') or {}
        allowlist={s.strip().casefold() for s in config.autopilot_allowlist.split(',') if s.strip()}
        if decision.action=='prepare_filing': status=CaseStatus.NEEDS_INFO
        elif case.facts_json.get('owner_controlled') and company and company.get('demo') and contact.get('email') and contact['email'].casefold() in allowlist:
            async with _send_lock:
                with Session(app.state.engine) as session:
                    current=session.get(Case,case_id)
                    if not current: return
                    current_messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
                    current.level=new_level
                    timestamp=now(session) if company.get('demo') and config.demo_mode else datetime.now(timezone.utc)
                    reason,due=guard(current,current_messages,timestamp,config,bool(company.get('demo')))
                    if reason:
                        current.level=case.level
                        if due:
                            current.facts_json={**current.facts_json,'pending_action':{'category':analysis.category if analysis else 'acknowledged','breached':breached,'redress_breached':redress_breached,'promise_expired':promise_expired,'due_at':due.isoformat()}}
                            session.add(current)
                        elif current.facts_json.get('paused') and analysis:
                            current.facts_json={**current.facts_json,'pending_review':analysis.model_dump()};session.add(current)
                        session.add(Event(case_id=case_id,actor='system',type='send_limit',title='Follow-up deferred' if due else 'Sending stopped',reason=reason,payload_json={'next_allowed_at':due.isoformat() if due else None}));session.commit()
                    previous=next((m for m in reversed(current_messages) if m.direction=='out'),None)
                if reason:
                    await app.state.events.publish('case_changed',{'case_id':case_id})
                    return
                try:
                    message_id=await send_email(contact,draft.subject,draft.body,False,True,previous.message_id if previous else None,[m.message_id for m in current_messages if m.message_id],case_id)
                except Exception as error:
                    from .mail.delivery import permanently_blocked,record_blocked
                    if not permanently_blocked(error): raise
                    record_blocked(app.state.engine,case_id)
                    await app.state.events.publish('case_changed',{'case_id':case_id})
                    return
                from .mail.tracking import tracked_subject
                outgoing=Message(case_id=case.id,direction='out',level=new_level,to=contact['email'],from_=config.user_email,subject=tracked_subject(draft.subject,case.id),body_text=draft.body,message_id=message_id,sent_at=timestamp)
                status=CaseStatus.ESCALATED if decision.action=='escalate' else CaseStatus.WAITING
                async with _write_lock:
                    with Session(app.state.engine) as session:
                        current=session.get(Case,case_id)
                        if not current: return
                        current.facts_json={k:v for k,v in current.facts_json.items() if k!='pending_action'}
                        if promise and promise.get('exceeds_redress') and decision.action=='followup': current.facts_json={**current.facts_json,'promise':{**promise,'pushback_sent':True}}
                        current.level=new_level;current.status=status;session.add(current);session.add(outgoing);session.add(event)
                        session.add(Event(case_id=case.id,actor='ai',type='draft',title='Next action drafted',reason=decision.reason,payload_json=draft.model_dump()))
                        if breached and decision.action=='followup': session.add(Deadline(case_id=case_id,kind='followup',due_at=timestamp+timedelta(hours=48)))
                        session.commit()
            if config.user_email_app_password.get_secret_value():
                from .mail.threading_gmail import schedule_sent_lookup
                schedule_sent_lookup(app.state.engine,message_id)
            await app.state.events.publish('decision',{'case_id':case.id,'action':decision.action,'reason':decision.reason})
            return
        else: status=CaseStatus.AWAITING_APPROVAL
    async with _write_lock:
        with Session(app.state.engine) as session:
            current=session.get(Case,case_id)
            if not current or current.status==CaseStatus.RESOLVED or current.facts_json.get('paused'): return
            current.status=status;current.level=new_level;session.add(current);session.add(event)
            if draft:
                payload=draft.model_dump()
                if decision.action=='prepare_filing': payload['portal_url']='https://consumerhelpline.gov.in/public/'
                session.add(Event(case_id=case.id,actor='ai',type='nch_pack' if decision.action=='prepare_filing' else 'draft',title='NCH-ready complaint' if decision.action=='prepare_filing' else 'Next action drafted',reason=decision.reason,payload_json=payload))
            session.commit()
    await app.state.events.publish('decision',{'case_id':case.id,'action':decision.action,'reason':decision.reason})


async def receive(app, data: dict) -> None:
    from .mail.attach_debug import decision as log_decision
    with Session(app.state.engine) as session:
        existing=session.exec(select(Message).where(Message.message_id==data['message_id'])).first()
        case=session.get(Case,data['case_id'])
        if existing or not case or case.status==CaseStatus.RESOLVED or case.facts_json.get('verification_paused'):
            reason='already stored' if existing else 'case missing' if not case else 'case resolved' if case.status==CaseStatus.RESOLVED else 'verification paused'
            log_decision(data['case_id'],data['message_id'],data.get('match_method'),'skipped',reason);return
    if data.get('needs_confirmation') and not data.get('user_confirmed'):
        async with _send_lock:
            with Session(app.state.engine) as session:
                if any(e.payload_json.get('message_id')==data['message_id'] for e in session.exec(select(Event).where(Event.case_id==data['case_id'],Event.type=='candidate_pending')).all()): return
                pending_case=session.get(Case,data['case_id'])
                if not pending_case: return
                if data.get('bounced'):
                    pending_case.facts_json={**pending_case.facts_json,'possible_bounce':True};session.add(pending_case)
                reason='Unverified sender; confirm before any action.' if not data.get('sender_verified') else 'Matched by company domain only; confirm this belongs to the case.'
                session.add(Event(case_id=data['case_id'],actor='system',type='candidate_pending',title='Unverified sender' if not data.get('sender_verified') else 'Confirm this email',reason=reason,payload_json={**data,'reviewed':False}));session.commit()
        log_decision(data['case_id'],data['message_id'],data.get('match_method'),'pending_review',reason)
        await app.state.events.publish('case_changed',{'case_id':data['case_id']})
        return
    if data.get('bounced'):
        async with _send_lock:
            with Session(app.state.engine) as session:
                case=session.get(Case,data['case_id'])
                if not case or session.exec(select(Message).where(Message.message_id==data['message_id'])).first(): return
                case.facts_json={**case.facts_json,'recipient_bounced':True};session.add(case)
                session.add(Message(case_id=case.id,direction='in',level=case.level,to=app.state.config.user_email,from_=data['sender'],subject=data['subject'],body_text=data['body'],message_id=data['message_id'],in_reply_to=data.get('in_reply_to'),references_json=data.get('references',[]),gmail_thread_id=data.get('gmail_thread_id'),match_method=data.get('match_method'),classification_json={'category':'bounce'},sent_at=now(session)))
                session.add(Evidence(case_id=case.id,kind='email',transcript=data['body'],extracted_json={'origin':'bounce','message_id':data['message_id']}))
                session.add(Event(case_id=case.id,actor='system',type='bounce',title='Recipient bounced',reason='Delivery failure detected; emailing stopped and NCH preparation required.',payload_json={'message_id':data['message_id']}));session.commit()
        await app.state.events.publish('case_changed',{'case_id':data['case_id']})
        await act(app,data['case_id'])
        return
    analysis=await classify_reply(data['body'],case.amount_inr,case.demand)
    async with _write_lock:
        with Session(app.state.engine) as session:
            current=session.get(Case,case.id)
            if not current or session.exec(select(Message).where(Message.message_id==data['message_id'])).first(): return
            reported=data.get('origin')=='user-reported'
            reply_level=Level(data['reply_level']) if data.get('reply_level') in ('L2','L3','L4','L5') else current.level
            stale=reply_level!=current.level and analysis.category in ('deflection','acknowledged','auto_reply')
            if current.facts_json.get('paused'):
                current.facts_json={**current.facts_json,'pending_review':analysis.model_dump()};session.add(current)
            classification={**analysis.model_dump(),'sender_verified':bool(data.get('sender_verified')),'verification_detail':data.get('verification_detail') or ('Simulated reply' if data.get('simulated') else 'User-reported update' if reported else 'Unverified sender'),'match_method':'user_confirmed' if data.get('user_confirmed') else data.get('match_method'),'label_applied':bool(data.get('label_applied'))}
            session.add(Message(case_id=case.id,direction='in',level=reply_level,to=app.state.config.user_email,from_=data['sender'],subject=data['subject'],body_text=data['body'],message_id=data['message_id'],in_reply_to=data.get('in_reply_to'),references_json=data.get('references',[]),gmail_thread_id=data.get('gmail_thread_id'),match_method='user_confirmed' if data.get('user_confirmed') else data.get('match_method'),classification_json=classification,sent_at=now(session)))
            if stale: session.add(Event(case_id=case.id,actor='system',type='late_reply',title='Earlier-level reply recorded',reason='A late reply to an earlier escalation level does not trigger another follow-up.'))
            if analysis.ticket_id and analysis.ticket_id.casefold() in data['body'].casefold():
                current.facts_json={**current.facts_json,'known_ticket_ids':list(dict.fromkeys([*current.facts_json.get('known_ticket_ids',[]),analysis.ticket_id]))};session.add(current)
            if reported: session.add(Evidence(case_id=case.id,kind='text',transcript=data['body'],extracted_json={'origin':'user-reported','classification':analysis.model_dump()}))
            session.add(Event(case_id=case.id,actor='user' if reported else 'company',type='reply',title=('User-reported: ' if reported else 'Simulated reply: ' if data.get('simulated') else '')+analysis.category,reason=analysis.summary_hinglish,payload_json={'origin':'user-reported' if reported else 'email','folder':data.get('folder'),'message_id':data['message_id'],'simulated':bool(data.get('simulated')),'match_method':'user_confirmed' if data.get('user_confirmed') else data.get('match_method'),'label_applied':bool(data.get('label_applied'))}))
            if analysis.reply_type not in ('partial_offer','rejection'):
                from .engine.promises import promise_from_reply
                redress=session.exec(select(Deadline).where(Deadline.case_id==case.id,Deadline.kind=='resolve_30d',Deadline.status=='running')).first()
                clock=now(session) if current.facts_json.get('demo_sample') and app.state.config.demo_mode else datetime.now(timezone.utc)
                promise=promise_from_reply(data['body'],analysis.promised_date,clock,redress.due_at if redress else None)
                if promise:
                    details={'promised_date':promise.promised_date.isoformat(),'grace_until':promise.grace_until.isoformat(),'quote':promise.quote,'exceeds_redress':promise.exceeds_redress,'redress_date':redress.due_at.date().isoformat() if redress else None,'redress_at':redress.due_at.replace(tzinfo=timezone.utc).isoformat() if redress else None,'pushback_sent':False}
                    current.facts_json={**current.facts_json,'promise':details};session.add(current)
                    for old in session.exec(select(Deadline).where(Deadline.case_id==case.id,Deadline.kind=='promise',Deadline.status=='running')).all(): old.status='superseded';session.add(old)
                    if not promise.exceeds_redress: session.add(Deadline(case_id=case.id,kind='promise',due_at=promise.grace_until))
                    session.add(Event(case_id=case.id,actor='company',type='promise',title='Company promised an action',reason=promise.quote,payload_json=details))
            if analysis.acknowledged:
                for item in session.exec(select(Deadline).where(Deadline.case_id==case.id,Deadline.kind.in_(['ack_48h','followup']),Deadline.status=='running')).all(): item.status='met';session.add(item)
            session.commit()
    log_decision(case.id,data['message_id'],data.get('match_method'),'attached','stored inbound message'+('; earlier escalation level' if stale else ''))
    await app.state.events.publish('case_changed',{'case_id':case.id})
    if not stale: await act(app,case.id,analysis)


async def retry_imap(operation, *args):
    import imaplib
    for attempt, delay in enumerate((2, 5, 10)):
        try:
            return await asyncio.to_thread(operation, *args)
        except (TimeoutError, OSError, imaplib.IMAP4.abort) as error:
            logger.warning('IMAP transient failure: %s attempt=%s', type(error).__name__, attempt+1)
            if attempt == 2: raise
            await asyncio.sleep(delay)


async def inbox_iteration(app) -> None:
    from .mail.threading_gmail import schedule_sent_lookup
    with Session(app.state.engine) as session:
        active={c.id for c in session.exec(select(Case)).all() if c.status!=CaseStatus.RESOLVED and not c.facts_json.get('verification_paused')}
        missing=[m.message_id for m in session.exec(select(Message).where(Message.direction=='out',Message.gmail_thread_id==None)).all() if m.message_id and m.case_id in active]
    if app.state.config.user_email_app_password.get_secret_value():
        for mid in missing: schedule_sent_lookup(app.state.engine,mid)
    for data in await asyncio.to_thread(poll,app.state.engine):
        await receive(app,data)


async def inbox_loop(app) -> None:
    while True:
        config=get_settings()
        if config.user_email and config.user_email_app_password.get_secret_value():
            try: await inbox_iteration(app)
            except Exception as error:
                worker_failure(app,'inbox',error)
        await asyncio.sleep(2)


async def deadline_iteration(app) -> None:
    triggers=[];pending=[]
    async with _write_lock:
        with Session(app.state.engine) as session:
            timestamp=now(session)
            for item in session.exec(select(Deadline).where(Deadline.status=='running')).all():
                case=session.get(Case,item.case_id)
                if not case or case.status==CaseStatus.RESOLVED or case.facts_json.get('paused'): continue
                current=timestamp if case.facts_json.get('demo_sample') and app.state.config.demo_mode else datetime.now(timezone.utc)
                if item.due_at.replace(tzinfo=timezone.utc)<=current:
                    item.status='breached';session.add(item)
                    session.add(Event(case_id=case.id,actor='system',type='deadline',title='Deadline breached',reason=f'{item.kind} deadline expired.'))
                    if case.status!=CaseStatus.AWAITING_APPROVAL and item.kind in ('ack_48h','followup','resolve_30d','promise'): triggers.append((case.id,item.kind))
            for case in session.exec(select(Case)).all():
                entry=case.facts_json.get('pending_action')
                if entry and not case.facts_json.get('paused'):
                    current=timestamp if case.facts_json.get('demo_sample') and app.state.config.demo_mode else datetime.now(timezone.utc)
                    if datetime.fromisoformat(entry['due_at'])<=current: pending.append((case.id,entry))
            session.commit()
    for case_id,kind in triggers: await act(app,case_id,breached=kind in ('ack_48h','followup'),redress_breached=kind=='resolve_30d',promise_expired=kind=='promise')
    for case_id,entry in pending:
        analysis=ReplyAnalysis(reply_type='deflection' if entry['category']=='deflection' else 'acknowledgment',acknowledged=True,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='',reason='',category=entry['category'])
        await act(app,case_id,analysis,breached=entry['breached'],redress_breached=entry['redress_breached'],promise_expired=entry.get('promise_expired',False))


async def deadline_loop(app) -> None:
    while True:
        try: await deadline_iteration(app)
        except Exception as error:
            worker_failure(app,'deadlines',error)
        await asyncio.sleep(10)
