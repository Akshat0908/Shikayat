from datetime import timedelta
from fastapi import APIRouter, HTTPException, Request
from sqlmodel import Session, select
from pydantic import BaseModel, Field
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
        if case.status==CaseStatus.AWAITING_APPROVAL:
            existing=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
            if existing: return EmailDraft.model_validate(existing.payload_json)
        if case.status!=CaseStatus.DRAFT: raise HTTPException(409,'Case is not ready for a new draft')
        deadline=now(session)+timedelta(days=30)
    try:
        result=await draft_complaint(case,deadline)
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
    if not edit.body.strip(): raise HTTPException(422,'Draft body cannot be blank')
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.status!=CaseStatus.AWAITING_APPROVAL: raise HTTPException(409,'Case is not awaiting approval')
        previous=session.exec(select(Event).where(Event.case_id==case_id,Event.type=='draft').order_by(Event.at.desc())).first()
        if not previous: raise HTTPException(409,'Create a draft first')
        updated=EmailDraft.model_validate({**previous.payload_json,'body':edit.body})
        session.add(Event(case_id=case_id,actor='user',type='draft',title='Complaint edited',reason='User edited the complaint before approval.',payload_json=updated.model_dump()))
        session.commit()
    await request.app.state.events.publish('draft',{'case_id':case_id,'reason':'User edited draft'})
    return updated

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
    with Session(request.app.state.engine) as session:
        from ..config import get_settings
        sent_at=now(session)
        session.add(Message(case_id=case_id,direction='out',level=case.level,to=contact['email'],from_=get_settings().user_email,subject=email.subject,body_text=email.body,message_id=message_id,sent_at=sent_at))
        if previous is None and company.get('sector')=='e-commerce':
            # SMTP acceptance is not proof of complaint receipt; deadlines are provisional.
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

@router.get('/{case_id}/verification')
def verification(case_id: str, request: Request) -> dict:
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        events=session.exec(select(Event).where(Event.case_id==case_id).order_by(Event.at)).all()
        messages=session.exec(select(Message).where(Message.case_id==case_id).order_by(Message.sent_at)).all()
        return {'case':case.model_dump(mode='json'),'events':[e.model_dump(mode='json') for e in events],'messages':[{'direction':m.direction,'message_id':m.message_id,'in_reply_to':m.in_reply_to,'level':m.level,'classification':m.classification_json} for m in messages],'worker_errors':getattr(request.app.state,'worker_errors',{})}

@router.get('')
def list_cases(request: Request) -> list[Case]:
    with Session(request.app.state.engine) as session:
        return list(session.exec(select(Case).order_by(Case.created_at.desc())).all())

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
        return {'case':case.model_dump(mode='json'),'events':[e.model_dump(mode='json') for e in events], 'messages':[m.model_dump(mode='json') for m in messages], 'deadlines':[d.model_dump(mode='json') for d in deadlines_], 'now':now(session).isoformat(), 'sender':get_settings().user_email or None,'recipient':contact,'sector_message':None if company and company.get('sector')=='e-commerce' else 'Sector-specific rules not configured'}
