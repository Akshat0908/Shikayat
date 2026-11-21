from uuid import uuid4
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel
from sqlmodel import Session,select,delete
from ..config import get_settings
from ..models import Case,CaseStatus,Deadline,Evidence,Event,Message,Settings
from ..demo.clock import now
from ..demo.company_bot import REPLIES
from ..workers import receive
router=APIRouter(prefix='/api/demo')

class CaseInput(BaseModel):
    case_id: str

def enabled() -> None:
    if not get_settings().demo_mode: raise HTTPException(403,'Demo mode disabled')

@router.post('/clock')
async def clock(request: Request) -> dict:
    enabled()
    with Session(request.app.state.engine) as session:
        settings=session.get(Settings,1);settings.demo_clock_offset_seconds+=48*3600;session.add(settings);session.commit()
        timestamp=now(session).isoformat()
    await request.app.state.events.publish('clock',{'now':timestamp})
    return {'now':timestamp}

@router.post('/inject')
async def inject(data: CaseInput,request: Request) -> dict:
    enabled()
    with Session(request.app.state.engine) as session:
        case=session.get(Case,data.case_id)
        if not case or case.company_id!='shopkart': raise HTTPException(422,'Injection is only available for ShopKart demo cases')
        messages=session.exec(select(Message).where(Message.case_id==case.id,Message.direction=='out').order_by(Message.sent_at)).all()
        if not messages: raise HTTPException(409,'Approve and send the complaint first')
        count=len(session.exec(select(Message).where(Message.case_id==case.id,Message.direction=='in')).all())
        if count>=3: raise HTTPException(409,'All scripted replies already injected')
        last=messages[-1]
        payload=dict(case_id=case.id,message_id=f'<demo-{uuid4()}>',sender=last.to,subject='Re: '+last.subject,body=REPLIES[count].format(amount=case.amount_inr),in_reply_to=last.message_id)
    await receive(request.app,payload)
    return {'status':'injected'}

@router.post('/reset')
async def reset(request: Request) -> dict:
    enabled()
    with Session(request.app.state.engine) as session:
        ids=[c.id for c in session.exec(select(Case).where(Case.company_id=='shopkart')).all() if c.facts_json.get('demo_sample')]
        for model in (Deadline,Evidence,Event,Message): session.exec(delete(model).where(model.case_id.in_(ids)))
        session.exec(delete(Case).where(Case.id.in_(ids)))
        settings=session.get(Settings,1);settings.demo_clock_offset_seconds=0;session.add(settings);session.commit()
    return {'status':'reset','cases_deleted':len(ids)}
