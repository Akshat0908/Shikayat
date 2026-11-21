from datetime import timedelta
from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session, select
from ..ai.draft_complaint import EmailDraft, draft_complaint
from ..demo.clock import now
from ..engine.company import load_companies
from ..engine.deadlines import deadlines
from ..mail.smtp_send import send_email
from ..models import Case, CaseStatus, Deadline, Event, Message

router=APIRouter(prefix='/api/cases')

@router.post('/{case_id}/draft')
async def draft(case_id: str, request: Request) -> EmailDraft:
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        try:
            result=await draft_complaint(case,now(session)+timedelta(days=30))
        except ValueError as e: raise HTTPException(503,str(e)) from e
        session.add(Event(case_id=case.id,actor='ai',type='draft',title='Complaint drafted',reason='Only verified references were supplied; deadline computed in code.',payload_json=result.model_dump()))
        case.status=CaseStatus.AWAITING_APPROVAL;session.add(case);session.commit()
    await request.app.state.events.publish('draft',{'case_id':case_id,'reason':'Ready for user approval'})
    return result

@router.post('/{case_id}/approve')
async def approve(case_id: str, request: Request) -> dict[str,str]:
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
        previous=session.exec(select(Message).where(Message.case_id==case_id,Message.direction=='out').order_by(Message.sent_at.desc())).first()
        try:
            message_id=await send_email(contact,email.subject,email.body,True,company.get('demo',False),previous.message_id if previous else None)
        except ValueError as e: raise HTTPException(422,str(e)) from e
        from ..config import get_settings
        sent_at=now(session)
        session.add(Message(case_id=case_id,direction='out',level=case.level,to=contact['email'],from_=get_settings().user_email,subject=email.subject,body_text=email.body,message_id=message_id,sent_at=sent_at))
        if previous is None:
            for kind,due in deadlines(sent_at).items(): session.add(Deadline(case_id=case_id,kind=kind,due_at=due))
        session.add(Event(case_id=case_id,actor='user',type='sent',title='Complaint sent',reason='User explicitly approved this draft.',payload_json={'message_id':message_id}))
        case.status=CaseStatus.WAITING;session.add(case);session.commit()
    await request.app.state.events.publish('sent',{'case_id':case_id,'reason':'Approved complaint delivered to SMTP'})
    return {'message_id':message_id}

@router.get('/{case_id}')
def get_case(case_id: str, request: Request) -> Case:
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        return case

@router.post('/{case_id}/confirm-receipt')
async def receipt(case_id: str, request: Request) -> Case:
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
