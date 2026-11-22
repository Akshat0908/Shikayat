from ..engine.sector import effective_sector
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session,select
from ..ai.draft_complaint import EmailDraft
from ..demo.clock import now
from ..engine.company import load_companies
from ..engine.deadlines import deadlines
from ..engine.send_guard import guard
from ..mail.tracking import case_tag,plus_address,tracked_subject,compose_urls
from ..models import Case,CaseStatus,Deadline,Event,Message,UserProfile
from .admin import is_admin

router=APIRouter(prefix='/api/cases')


def prepared(session: Session, request: Request, case_id: str) -> tuple[Case,dict,EmailDraft,list[Message],datetime,str]:
    case=session.get(Case,case_id)
    if not case: raise HTTPException(404,'Case not found')
    if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Case is not awaiting approval')
    company=next((c for c in load_companies() if c['id']==case.company_id),None)
    if not company or case.level.value not in ('L2','L3'): raise HTTPException(422,'Recipient requires review')
    contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
    if not contact.get('verified') or not contact.get('email'): raise HTTPException(422,'Recipient requires verification')
    config=request.app.state.config
    if not config.send_enabled: raise HTTPException(403,'Sending is disabled')
    messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
    timestamp=now(session) if company.get('demo') and config.demo_mode else datetime.now(timezone.utc)
    reason,_=guard(case,messages,timestamp,config,bool(company.get('demo')))
    if reason: raise HTTPException(409,reason)
    if not any(m.direction=='out' for m in messages):
        confirmed=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='recipient_confirmed').order_by(Event.at.desc())).first()
        fingerprint=hashlib.sha256(contact['email'].strip().casefold().encode()).hexdigest()
        if not confirmed or confirmed.payload_json.get('contact_hash')!=fingerprint or confirmed.payload_json.get('level')!=case.level.value: raise HTTPException(409,'Confirm the verified recipient before sending')
    event=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
    if not event: raise HTTPException(409,'Create a draft first')
    draft=EmailDraft.model_validate(event.payload_json)
    if not is_admin(request):
        from ..ai.draft_complaint import prepare_email
        draft=prepare_email(draft,case.facts_json,UserProfile(name='',phone='',email=''),company)
    if '[' in draft.body or '[' in draft.subject: raise HTTPException(422,'Remove placeholders from the draft')
    try: tracking=plus_address(config.user_email,case_id)
    except ValueError as error: raise HTTPException(422,str(error)) from error
    return case,company,draft,messages,timestamp,tracking

@router.post('/{case_id}/preview-compose')
async def preview_compose(case_id: str,request: Request) -> dict:
    """Open an explicitly labelled sandbox email in the visitor's own mail app."""
    from ..ai.sample_detection import ensure_sample_scan
    from ..ai.draft_complaint import prepare_email
    await ensure_sample_scan(request.app.state.engine,case_id)
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.facts_json.get('paused'): raise HTTPException(409,'Case is paused')
        if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Create a draft first')
        company=next((c for c in load_companies() if c['id']==case.company_id),None)
        contact=(company or {}).get('nodal_officer' if case.level.value=='L3' else 'grievance_officer') or {}
        if not case.facts_json.get('looks_like_sample') and contact.get('verified') and contact.get('email'):
            raise HTTPException(409,'Preview is available for test evidence or unverified contacts')
        event=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
        if not event: raise HTTPException(409,'Create a draft first')
        config=request.app.state.config
        if not config.send_enabled or not config.demo_company_email: raise HTTPException(403,'Sandbox preview is unavailable')
        email=prepare_email(EmailDraft.model_validate(event.payload_json),case.facts_json,UserProfile(name='',phone='',email=''),company)
        name=' '.join(str((company or {}).get('name') or case.facts_json.get('company_name') or 'unknown company').split())[:100]
        tracking=plus_address(config.user_email,case_id)
        subject=tracked_subject(f'[TEST — would go to {name}] {email.subject}',case_id)
        return {**compose_urls(config.demo_company_email,subject,email.body,tracking),'tracking_address':tracking,'note':'Send this labelled preview to the sandbox, then confirm below to start test tracking. Ask for a reply-all so the tracking address stays copied.'}

@router.post('/{case_id}/preview-sent')
async def preview_sent(case_id: str,request: Request) -> dict:
    """Track a user-confirmed manual sandbox send; its external Message-ID is unavailable."""
    from urllib.parse import parse_qs,urlparse
    from ..workers import _send_lock
    payload=await preview_compose(case_id,request)
    fields=parse_qs(urlparse(payload['mailto']).query)
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            case=session.get(Case,case_id)
            if not case: raise HTTPException(404,'Case not found')
            if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Case is not awaiting approval')
            config=request.app.state.config
            timestamp=datetime.now(timezone.utc)
            company=next((c for c in load_companies() if c['id']==case.company_id),None)
            session.add(Message(case_id=case_id,direction='out',level=case.level,to=config.demo_company_email,from_='User’s email app',subject=fields['subject'][0],body_text=fields['body'][0],message_id=None,sent_at=timestamp))
            if effective_sector(company,case.facts_json)=='e-commerce':
                for kind,due in deadlines(timestamp).items(): session.add(Deadline(case_id=case_id,kind=kind,due_at=due))
            case.facts_json={**case.facts_json,'sandbox_test':True,'owner_controlled':False};case.status=CaseStatus.WAITING;session.add(case)
            session.add(Event(case_id=case_id,actor='user',type='sent',title='Sent (sandbox test)',reason='User confirmed sending a labelled preview from their email app; the external Message-ID is not available.',payload_json={'manual':True,'sandbox_test':True,'tracking_address':payload['tracking_address']}));session.commit()
    await request.app.state.events.publish('case_changed',{'case_id':case_id})
    return {'status':'sandbox_tracking_started'}

@router.post('/{case_id}/manual-compose')
async def manual_compose(case_id: str,request: Request) -> dict:
    from ..ai.sample_detection import ensure_sample_scan
    await ensure_sample_scan(request.app.state.engine,case_id)
    with Session(request.app.state.engine) as session:
        case,company,draft,_,_,tracking=prepared(session,request,case_id)
        contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
        return {**compose_urls(contact['email'],tracked_subject(draft.subject,case_id),draft.body,tracking),'tracking_address':tracking,'note':'The tracking address is included in CC. Ask the company to reply all or forward replies here; replies to you alone cannot be tracked.'}

@router.post('/{case_id}/manual-sent')
async def manual_sent(case_id: str,request: Request) -> dict:
    from ..ai.sample_detection import ensure_sample_scan
    await ensure_sample_scan(request.app.state.engine,case_id)
    from ..workers import _send_lock
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            case,company,draft,messages,timestamp,tracking=prepared(session,request,case_id)
            contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
            prior=any(m.direction=='out' for m in messages)
            session.add(Message(case_id=case.id,direction='out',level=case.level,to=contact['email'],from_='User’s email app',subject=tracked_subject(draft.subject,case_id),body_text=draft.body,message_id=None,sent_at=timestamp))
            if not prior and effective_sector(company,case.facts_json)=='e-commerce':
                for kind,due in deadlines(timestamp).items(): session.add(Deadline(case_id=case_id,kind=kind,due_at=due))
            session.add(Event(case_id=case_id,actor='user',type='sent',title='Sent by user (manual)',reason='User confirmed they sent the complaint from their email app.',payload_json={'manual':True,'tracking_address':tracking,'case_tag':case_tag(case_id)}))
            promise=case.facts_json.get('promise')
            if promise and promise.get('exceeds_redress') and not promise.get('pushback_sent'):
                case.facts_json={**case.facts_json,'promise':{**promise,'pushback_sent':True}}
            case.facts_json={**case.facts_json,'owner_controlled':False}
            case.status=CaseStatus.WAITING;session.add(case);session.commit()
    await request.app.state.events.publish('sent',{'case_id':case_id,'reason':'User confirmed manual send'})
    return {'status':'sent_by_user'}
