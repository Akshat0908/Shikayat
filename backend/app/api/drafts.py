from datetime import timedelta
import hashlib
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from ..ai.draft_complaint import EmailDraft, draft_complaint, prepare_email, validate_draft
from ..demo.clock import now
from ..engine.company import load_companies
from ..engine.sector import effective_sector, sector_message
from ..engine.deadlines import deadlines
from ..mail.smtp_send import send_email
from ..models import Case, CaseStatus, Deadline, Event, Message, Evidence, UserProfile
from .admin import require_admin, is_admin

router=APIRouter(prefix='/api/cases')

@router.post('/{case_id}/draft')
async def draft(case_id: str, request: Request) -> EmailDraft:
    from ..ai.sample_detection import ensure_sample_scan
    await ensure_sample_scan(request.app.state.engine,case_id)
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.status==CaseStatus.AWAITING_APPROVAL:
            existing=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
            if existing:
                from ..api.profile import get_profile
                profile=get_profile(session,request.app.state.config.user_email) if is_admin(request) else UserProfile(name='',phone='',email='')
                company=next((item for item in load_companies() if item['id']==case.company_id),None)
                result=prepare_email(EmailDraft.model_validate(existing.payload_json),case.facts_json,profile,company)
                if is_admin(request) and result.model_dump()!=existing.payload_json:
                    session.add(Event(case_id=case_id,actor='system',type='draft',title='Complaint updated',reason='Profile and citation details refreshed.',payload_json=result.model_dump()));session.commit()
                return result
        if case.status!=CaseStatus.DRAFT: raise HTTPException(409,'Case is not ready for a new draft')
        from ..api.profile import get_profile
        profile=get_profile(session,request.app.state.config.user_email) if is_admin(request) else UserProfile(name='',phone='',email='')
        company=next((item for item in load_companies() if item["id"]==case.company_id),None)
        from ..engine.deadlines import deadlines as compute_deadlines
        deadline=compute_deadlines(now(session))["resolve_30d"]
    try:
        result=prepare_email(await draft_complaint(case,deadline),case.facts_json,profile,company)
        validate_draft(result,deadline.date().isoformat())
    except ValueError as e: raise HTTPException(503,str(e)) from e
    with Session(request.app.state.engine) as session:
        session.add(Event(case_id=case.id,actor='ai',type='draft',title='Complaint drafted',reason='Only verified references were supplied; deadline computed in code.',payload_json=result.model_dump()))
        case.status=CaseStatus.AWAITING_APPROVAL;session.add(case);session.commit()
    await request.app.state.events.publish('draft',{'case_id':case_id,'reason':'Ready for user approval'})
    return result

class DraftEdit(BaseModel):
    body: str = Field(min_length=1, max_length=20000)

@router.patch('/{case_id}/draft')
async def edit_draft(case_id: str, edit: DraftEdit, request: Request) -> EmailDraft:
    if not edit.body.strip() or '[' in edit.body: raise HTTPException(422,'Draft must not contain placeholders')
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Case is not awaiting approval')
        previous=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
        if not previous: raise HTTPException(409,'Create a draft first')
        from ..api.profile import get_profile
        profile=get_profile(session,request.app.state.config.user_email) if is_admin(request) else UserProfile(name='',phone='',email='')
        company=next((item for item in load_companies() if item['id']==case.company_id),None)
        updated=prepare_email(EmailDraft.model_validate({**previous.payload_json,'body':edit.body}),case.facts_json,profile,company)
        session.add(Event(case_id=case_id,actor='user',type='draft',title='Complaint edited',reason='User edited the complaint before approval.',payload_json=updated.model_dump()))
        session.commit()
    await request.app.state.events.publish('draft',{'case_id':case_id,'reason':'User edited draft'})
    return updated

@router.post('/{case_id}/approve',dependencies=[Depends(require_admin)])
async def approve(case_id: str, request: Request) -> dict[str,str]:
    from ..ai.sample_detection import ensure_sample_scan
    await ensure_sample_scan(request.app.state.engine,case_id)
    from datetime import datetime, timezone
    from ..workers import _send_lock
    from ..engine.send_guard import guard
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            case=session.get(Case,case_id)
            if not case: raise HTTPException(404,'Case not found')
            if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Case is not awaiting approval')
            events=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).all()
            if not events: raise HTTPException(409,'Create a draft first')
            company=next((c for c in load_companies() if c['id']==case.company_id),None)
            if not company: raise HTTPException(422,'Company needs verification')
            if case.level.value not in ('L2','L3'): raise HTTPException(422,'Portal filings require manual submission')
            contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
            email=EmailDraft.model_validate(events[0].payload_json)
            if '[' in email.body or '[' in email.subject: raise HTTPException(422,'Edit the draft to remove placeholders before sending')
            messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
            previous=next((m for m in reversed(messages) if m.direction=='out'),None)
            config=request.app.state.config
            timestamp=now(session) if company.get('demo') and config.demo_mode else datetime.now(timezone.utc)
            reason,due=guard(case,messages,timestamp,config,bool(company.get('demo')),contact)
            if reason:
                session.add(Event(case_id=case_id,actor='system',type='send_limit',title='Sending stopped',reason=reason,payload_json={'next_allowed_at':due.isoformat() if due else None}));session.commit()
                raise HTTPException(409,reason)
            if previous is None:
                confirmed=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='recipient_confirmed').order_by(Event.at.desc())).first()
                fingerprint=hashlib.sha256((contact.get('email') or '').strip().casefold().encode()).hexdigest()
                if not confirmed or confirmed.payload_json.get('contact_hash')!=fingerprint or confirmed.payload_json.get('level')!=case.level.value:
                    raise HTTPException(409,'Confirm the verified recipient before the first send')
        try:
            message_id=await send_email(contact,email.subject,email.body,True,company.get('demo',False),previous.message_id if previous else None,None,case_id,bool(case.facts_json.get('looks_like_sample')))
        except ValueError as e: raise HTTPException(422,str(e)) from e
        except Exception as error:
            from ..mail.delivery import permanently_blocked,record_blocked
            if not permanently_blocked(error): raise
            record_blocked(request.app.state.engine,case_id)
            await request.app.state.events.publish('case_changed',{'case_id':case_id})
            raise HTTPException(422,'Recipient blocked; NCH-ready complaint prepared') from error
        with Session(request.app.state.engine) as session:
            current=session.get(Case,case_id)
            if not current: raise HTTPException(404,'Case not found')
            from ..mail.tracking import tracked_subject
            session.add(Message(case_id=case_id,direction='out',level=current.level,to=contact['email'],from_=config.user_email,subject=tracked_subject(('[TEST — sandbox] ' if current.facts_json.get('looks_like_sample') else '')+email.subject,case_id),body_text=email.body,message_id=message_id,sent_at=timestamp))
            if previous is None and effective_sector(company,current.facts_json)=='e-commerce':
                for kind,due in deadlines(timestamp).items(): session.add(Deadline(case_id=case_id,kind=kind,due_at=due))
            elif previous is not None and effective_sector(company,current.facts_json)=='e-commerce':
                missed=session.exec(select(Deadline).where(Deadline.case_id==case_id,Deadline.kind=='ack_48h',Deadline.status=='breached')).first()
                acknowledged=any(m.direction=='in' and m.level==current.level and m.classification_json.get('acknowledged') for m in messages)
                if missed and not acknowledged: session.add(Deadline(case_id=case_id,kind='followup',due_at=timestamp+timedelta(hours=48)))
            session.add(Event(case_id=case_id,actor='user',type='sent',title='Sandbox test sent' if current.facts_json.get('looks_like_sample') else 'Complaint sent',reason='User explicitly approved this sandbox test.' if current.facts_json.get('looks_like_sample') else 'User explicitly approved this draft.',payload_json={'message_id':message_id}))
            promise=current.facts_json.get('promise')
            if promise and promise.get('exceeds_redress') and not promise.get('pushback_sent'):
                current.facts_json={**current.facts_json,'promise':{**promise,'pushback_sent':True}}
            current.facts_json={**current.facts_json,'owner_controlled':True}
            current.status=CaseStatus.WAITING;session.add(current);session.commit()
    if config.user_email_app_password.get_secret_value():
        from ..mail.threading_gmail import schedule_sent_lookup
        schedule_sent_lookup(request.app.state.engine,message_id)
    await request.app.state.events.publish('sent',{'case_id':case_id,'reason':'Approved complaint delivered to SMTP'})
    return {'message_id':message_id}

@router.post('/{case_id}/test-send',dependencies=[Depends(require_admin)])
async def test_send(case_id: str, request: Request) -> dict:
    """Send an explicitly labelled preview only to the configured demo mailbox."""
    from ..ai.sample_detection import ensure_sample_scan
    await ensure_sample_scan(request.app.state.engine,case_id)
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.facts_json.get('paused'): raise HTTPException(409,'Case is paused')
        if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Create a draft first')
        company=next((c for c in load_companies() if c['id']==case.company_id),None)
        contact=(company or {}).get('nodal_officer' if case.level.value=='L3' else 'grievance_officer') or {}
        if not case.facts_json.get('looks_like_sample') and contact.get('verified') and contact.get('email'):
            raise HTTPException(409,'Test send is available for sample or unverified cases')
        event=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
        if not event: raise HTTPException(409,'Create a draft first')
        email=EmailDraft.model_validate(event.payload_json)
        name=' '.join(str((company or {}).get('name') or case.facts_json.get('company_name') or 'unknown company').split())[:100]
        config=request.app.state.config
        if not config.demo_company_email: raise HTTPException(422,'Demo inbox is not configured')
    subject=f'[TEST — would go to {name}] {email.subject}'
    try:
        message_id=await send_email({'email':config.demo_company_email,'verified':True},subject,email.body,True,True,case_id=case_id)
    except ValueError as error: raise HTTPException(422,str(error)) from error
    with Session(request.app.state.engine) as session:
        session.add(Event(case_id=case_id,actor='user',type='test_send',title='Test email sent to demo inbox',reason='Explicit test send; no company was contacted and no deadlines were started.',payload_json={'message_id':message_id,'simulated':True}));session.commit()
    await request.app.state.events.publish('case_changed',{'case_id':case_id})
    return {'status':'test_sent','recipient':'demo inbox','message_id':message_id}

@router.post('/{case_id}/confirm-recipient')
async def confirm_recipient(case_id: str, request: Request) -> dict:
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        company=next((c for c in load_companies() if c['id']==case.company_id),None)
        if not company or case.level.value not in ('L2','L3'): raise HTTPException(422,'Recipient requires review')
        contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
        if not contact.get('verified') or not contact.get('email'): raise HTTPException(422,'Recipient requires verification')
        digest=hashlib.sha256(contact['email'].strip().casefold().encode()).hexdigest()
        session.add(Event(case_id=case_id,actor='user',type='recipient_confirmed',title='Recipient confirmed',reason='User confirmed the verified recipient before sending.',payload_json={'contact_hash':digest,'level':case.level.value}));session.commit()
    await request.app.state.events.publish('case_changed',{'case_id':case_id})
    return {'status':'confirmed','source_url':contact.get('source_url'),'last_checked':contact.get('last_checked'),'verified':contact['verified']}

@router.get('/{case_id}')
def get_case(case_id: str, request: Request) -> Case:
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        return case

@router.post('/{case_id}/confirm-receipt')
async def receipt(case_id: str, request: Request) -> Case:
    from ..workers import _send_lock
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            case=session.get(Case,case_id)
            if not case: raise HTTPException(404,'Case not found')
            if case.status!=CaseStatus.AWAITING_RECEIPT: raise HTTPException(409,'No full resolution offer awaiting confirmation')
            case.status=CaseStatus.RESOLVED;case.resolved_at=now(session);case.recovered_inr=case.amount_inr or 0
            for deadline in session.exec(select(Deadline).where(Deadline.case_id==case_id,Deadline.status=='running')).all():
                deadline.status='met';session.add(deadline)
            session.add(case);session.add(Event(case_id=case_id,actor='user',type='resolved',title='Receipt confirmed',reason='User confirmed funds were received.'));session.commit();session.refresh(case)
    await request.app.state.events.publish('resolved',{'case_id':case_id,'reason':'Receipt confirmed by user'})
    return case

@router.get('/{case_id}/verification')
def verification(case_id: str, request: Request) -> dict:
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        events=session.exec(select(Event).where(Event.case_id==case_id).order_by(Event.at)).all()
        messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
        return {'case':case.model_dump(mode='json'),'events':[e.model_dump(mode='json') for e in events],'messages':[{'direction':m.direction,'message_id':m.message_id,'in_reply_to':m.in_reply_to,'references':m.references_json,'gmail_thread_id':m.gmail_thread_id,'match_method':m.match_method,'level':m.level,'classification':m.classification_json} for m in messages],'worker_errors':getattr(request.app.state,'worker_errors',{})}

@router.get('')
def list_cases(request: Request) -> list[Case]:
    with Session(request.app.state.engine) as session:
        from ..privacy import visible
        return [case for case in session.exec(select(Case).order_by(Case.created_at.desc())).all() if visible(request,case)]

@router.get('/{case_id}/board')
def case_board(case_id: str, request: Request) -> dict:
    from ..config import get_settings
    from ..demo.clock import now
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        events=session.exec(select(Event).where(Event.case_id==case_id).order_by(Event.at)).all()
        messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
        deadlines_=session.exec(select(Deadline).where(Deadline.case_id==case_id)).all()
        company=next((c for c in load_companies() if c['id']==case.company_id),None)
        contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer'] if company else None
        evidence=session.exec(select(Evidence).where(Evidence.case_id==case_id,Evidence.kind.in_(['screenshot','voice','text']))).all()
        config=request.app.state.config
        sent=[m for m in messages if m.direction=='out']; level_sent=[m for m in sent if m.level==case.level]
        limit=config.grievance_followup_limit if case.level.value=='L2' else config.nodal_followup_limit
        from datetime import datetime,timezone
        timestamp=now(session) if company and company.get('demo') and config.demo_mode else datetime.now(timezone.utc)
        from ..engine.send_guard import guard
        blocked,next_allowed=guard(case,messages,timestamp,config,bool(company and company.get('demo')))
        public_block=False
        return {'evidence':[{'id':e.id,'kind':e.kind,'transcript':e.transcript,'url':f'/api/cases/{case_id}/evidence/{e.id}/file' if e.path else None} for e in evidence], 'case':case.model_dump(mode='json'),'events':[e.model_dump(mode='json') for e in events], 'messages':[m.model_dump(mode='json') for m in messages], 'deadlines':[d.model_dump(mode='json') for d in deadlines_], 'now':timestamp.isoformat(), 'sender':(config.user_email or None) if is_admin(request) else None,'recipient':contact,'sector_message':sector_message(company,case.facts_json),'followups':{'count':max(0,len(level_sent)-1),'limit':limit,'next_allowed_at':next_allowed.isoformat() if next_allowed else None,'blocked_reason':blocked if not next_allowed else None},'sending_disabled':public_block}

class OfferResponse(BaseModel):
    action: Literal['accept','counter']
    counter_amount: float | None = Field(default=None, gt=0)

@router.post('/{case_id}/offer-response')
async def offer_response(case_id: str, response: OfferResponse, request: Request) -> dict:
    from ..ai.draft_escalation import draft_escalation
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.status!=CaseStatus.NEEDS_INFO: raise HTTPException(409,'No partial offer awaiting your choice')
        latest=session.exec(select(Message).where(Message.case_id==case_id,Message.direction=='in').order_by(Message.sent_at.desc())).first()
        if not latest or latest.classification_json.get('reply_type')!='partial_offer': raise HTTPException(409,'No partial offer awaiting your choice')
        if response.action=='counter' and response.counter_amount is None: raise HTTPException(422,'Counter amount is required')
        messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
        from ..api.profile import get_profile
        profile=get_profile(session,request.app.state.config.user_email) if is_admin(request) else UserProfile(name='',phone='',email='')
        company=next((item for item in load_companies() if item['id']==case.company_id),None)
        deadline=(now(session)+timedelta(days=2)).date().isoformat()
    reason=('User accepted the partial offer; request fulfillment and await confirmation.' if response.action=='accept' else f'User requested a counteroffer of INR {response.counter_amount:.2f}.')
    result=prepare_email(await draft_escalation(case.facts_json,[{'date':m.sent_at.date().isoformat(),'body':m.body_text} for m in messages],reason,deadline),case.facts_json,profile,company)
    validate_draft(result,deadline)
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if case.status!=CaseStatus.NEEDS_INFO: raise HTTPException(409,'Offer state changed')
        session.add(Event(case_id=case_id,actor='user',type='offer_response',title='Offer '+response.action,reason=reason,payload_json=response.model_dump()))
        session.add(Event(case_id=case_id,actor='ai',type='draft',title='Offer response drafted',reason=reason,payload_json=result.model_dump()))
        case.status=CaseStatus.AWAITING_APPROVAL;session.add(case);session.commit()
    await request.app.state.events.publish('case_changed',{'case_id':case_id})
    return {'status':'awaiting_approval','draft':result.model_dump()}
