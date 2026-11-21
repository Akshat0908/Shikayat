import asyncio
import logging
from datetime import timedelta, timezone
from sqlmodel import Session, select
from .ai.classify_reply import classify_reply, ReplyAnalysis
from .ai.draft_escalation import draft_escalation
from .config import get_settings
from .demo.clock import now
from .engine.company import load_companies
from .engine.policy import decide
from .mail.imap_poll import poll
from .mail.smtp_send import send_email
from .models import Case, CaseStatus, Deadline, Event, Level, Message

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


async def act(app, case_id: str, analysis: ReplyAnalysis | None = None, breached: bool = False) -> None:
    with Session(app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case or case.status==CaseStatus.RESOLVED or case.facts_json.get('verification_paused'): return
        messages=session.exec(select(Message).where(Message.case_id==case.id).order_by(Message.sent_at)).all()
        deflections=sum(m.classification_json.get('category')=='deflection' for m in messages if m.direction=='in')
        deadline=(now(session)+timedelta(days=2)).date().isoformat()
    company=next((c for c in load_companies() if c['id']==case.company_id),None)
    decision=decide(case.level.value,analysis.category if analysis else 'acknowledged',deflections,breached,analysis.offered_amount_inr if analysis else None,case.amount_inr,bool(case.facts_json.get('missing_info')),sector=company.get('sector') if company else None)
    event=Event(case_id=case.id,actor='ai',type='decision',title=decision.action,reason=decision.reason,payload_json={'action':decision.action,'level':decision.level,'requires_approval':decision.requires_approval})
    draft=None
    outgoing=None
    if decision.action=='confirm_receipt': case.status=CaseStatus.AWAITING_RECEIPT
    elif decision.action in ('ask_user','user_review','offer_choice'): case.status=CaseStatus.NEEDS_INFO
    elif decision.action in ('followup','escalate','counter','reply_info','prepare_filing'):
        case.level=Level(decision.level)
        draft=await draft_escalation(case.facts_json,[{'date':m.sent_at.date().isoformat(),'body':m.body_text} for m in messages],decision.reason,deadline)
        company=next((c for c in load_companies() if c['id']==case.company_id),None)
        contact=company['nodal_officer' if case.level==Level.L3 else 'grievance_officer'] if company else {}
        allowlist={s.strip().casefold() for s in get_settings().autopilot_allowlist.split(',') if s.strip()}
        if decision.action!='prepare_filing' and company and company.get('demo') and contact.get('email') and contact['email'].casefold() in allowlist:
            previous=next((m for m in reversed(messages) if m.direction=='out'),None)
            message_id=await send_email(contact,draft.subject,draft.body,False,True,previous.message_id if previous else None,[m.message_id for m in messages if m.message_id])
            outgoing=Message(case_id=case.id,direction='out',level=case.level,to=contact['email'],from_=get_settings().user_email,subject=draft.subject,body_text=draft.body,message_id=message_id)
            case.status=CaseStatus.ESCALATED if decision.action=='escalate' else CaseStatus.WAITING
        else: case.status=CaseStatus.AWAITING_APPROVAL
    async with _write_lock:
        with Session(app.state.engine) as session:
            session.add(event)
            if draft: session.add(Event(case_id=case.id,actor='ai',type='draft',title='Next action drafted',reason=decision.reason,payload_json=draft.model_dump()))
            if outgoing:
                outgoing.sent_at=now(session)
                session.add(outgoing)
            current=session.get(Case,case_id)
            if current.status!=CaseStatus.RESOLVED:
                current.status=case.status;current.level=case.level;session.add(current)
            session.commit()
    await app.state.events.publish('decision',{'case_id':case.id,'action':decision.action,'reason':decision.reason})


async def receive(app, data: dict) -> None:
    with Session(app.state.engine) as session:
        existing=session.exec(select(Message).where(Message.message_id==data['message_id'])).first()
        case=session.get(Case,data['case_id'])
        if existing or not case or case.status==CaseStatus.RESOLVED or case.facts_json.get('verification_paused'): return
    analysis=await classify_reply(data['body'],case.amount_inr,case.demand)
    async with _write_lock:
        with Session(app.state.engine) as session:
            if session.exec(select(Message).where(Message.message_id==data['message_id'])).first(): return
            session.add(Message(case_id=case.id,direction='in',level=case.level,to=get_settings().user_email,from_=data['sender'],subject=data['subject'],body_text=data['body'],message_id=data['message_id'],in_reply_to=data.get('in_reply_to'),classification_json=analysis.model_dump(),sent_at=now(session)))
            session.add(Event(case_id=case.id,actor='company',type='reply',title=('Simulated reply: ' if data.get('simulated') else '')+analysis.category,reason=analysis.summary_hinglish,payload_json={'folder':data.get('folder'),'message_id':data['message_id'],'simulated':bool(data.get('simulated'))}))
            if analysis.category in ('acknowledged','info_requested','resolution_offered'):
                for deadline in session.exec(select(Deadline).where(Deadline.case_id==case.id,Deadline.kind=='ack_48h',Deadline.status=='running')).all():
                    deadline.status='met';session.add(deadline)
            session.commit()
    await app.state.events.publish('case_changed',{'case_id':case.id})
    await act(app,case.id,analysis)


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
    for data in await retry_imap(poll,app.state.engine):
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
    triggers=[]
    async with _write_lock:
        with Session(app.state.engine) as session:
            timestamp=now(session)
            for deadline in session.exec(select(Deadline).where(Deadline.status=='running')).all():
                if deadline.due_at.replace(tzinfo=timezone.utc)<=timestamp:
                    deadline.status='breached';session.add(deadline)
                    case=session.get(Case,deadline.case_id)
                    if case and case.status not in (CaseStatus.RESOLVED,CaseStatus.AWAITING_APPROVAL) and deadline.kind=='ack_48h': triggers.append(case.id)
            session.commit()
    for case_id in triggers: await act(app,case_id,breached=True)


async def deadline_loop(app) -> None:
    while True:
        try: await deadline_iteration(app)
        except Exception as error:
            worker_failure(app,'deadlines',error)
        await asyncio.sleep(10)
