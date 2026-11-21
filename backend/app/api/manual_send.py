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
from ..models import Case,CaseStatus,Deadline,Event,Message

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
    if config.public_demo and (not company.get('demo') or contact['email'].strip().casefold() not in {s.strip().casefold() for s in config.autopilot_allowlist.split(',') if s.strip()}): raise HTTPException(403,'Sending disabled on the public demo')
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
    if '[' in draft.body or '[' in draft.subject: raise HTTPException(422,'Remove placeholders from the draft')
    try: tracking=plus_address(config.user_email,case_id)
    except ValueError as error: raise HTTPException(422,str(error)) from error
    return case,company,draft,messages,timestamp,tracking

@router.post('/{case_id}/manual-compose')
def manual_compose(case_id: str,request: Request) -> dict:
    with Session(request.app.state.engine) as session:
        case,company,draft,_,_,tracking=prepared(session,request,case_id)
        contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
        return {**compose_urls(contact['email'],tracked_subject(draft.subject,case_id),draft.body,tracking),'tracking_address':tracking,'note':'Your email app may not support Reply-To; the tracking address is included in CC.'}

@router.post('/{case_id}/manual-sent')
async def manual_sent(case_id: str,request: Request) -> dict:
    from ..workers import _send_lock
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            case,company,draft,messages,timestamp,tracking=prepared(session,request,case_id)
            contact=company['nodal_officer' if case.level.value=='L3' else 'grievance_officer']
            prior=any(m.direction=='out' for m in messages)
            session.add(Message(case_id=case.id,direction='out',level=case.level,to=contact['email'],from_=request.app.state.config.user_email,subject=tracked_subject(draft.subject,case_id),body_text=draft.body,message_id=None,sent_at=timestamp))
            if not prior and company.get('sector')=='e-commerce':
                for kind,due in deadlines(timestamp).items(): session.add(Deadline(case_id=case_id,kind=kind,due_at=due))
            session.add(Event(case_id=case_id,actor='user',type='sent',title='Sent by user (manual)',reason='User confirmed they sent the complaint from their email app.',payload_json={'manual':True,'tracking_address':tracking,'case_tag':case_tag(case_id)}))
            promise=case.facts_json.get('promise')
            if promise and promise.get('exceeds_redress') and not promise.get('pushback_sent'):
                case.facts_json={**case.facts_json,'promise':{**promise,'pushback_sent':True}}
            case.status=CaseStatus.WAITING;session.add(case);session.commit()
    await request.app.state.events.publish('sent',{'case_id':case_id,'reason':'User confirmed manual send'})
    return {'status':'sent_by_user'}
