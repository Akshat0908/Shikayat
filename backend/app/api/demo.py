from uuid import uuid4
from fastapi import APIRouter,HTTPException,Request,Depends
from pydantic import BaseModel, Field
from sqlmodel import Session,select,delete
from ..config import get_settings
from ..models import Case,CaseStatus,Deadline,Evidence,Event,Message,Settings
from ..demo.clock import now
from ..demo.company_bot import REPLIES
from ..workers import receive
from .admin import require_admin
router=APIRouter(prefix='/api/demo',dependencies=[Depends(require_admin)])

class CaseInput(BaseModel):
    case_id: str
    text: str | None = Field(default=None, max_length=10000)

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

@router.post('/start')
async def start_simulation(data: CaseInput, request: Request) -> dict:
    """Create a clearly marked local-only outbound record; never send mail."""
    enabled()
    if request.app.state.config.send_enabled:
        raise HTTPException(403, 'Simulated tracking requires SEND_ENABLED=false')
    with Session(request.app.state.engine) as session:
        case=session.get(Case,data.case_id)
        if not case or case.company_id!='shopkart' or not case.facts_json.get('demo_sample'):
            raise HTTPException(422,'Simulation is only available for ShopKart sample cases')
        if session.exec(select(Message).where(Message.case_id==case.id,Message.direction=='out')).first():
            raise HTTPException(409,'Tracking already started')
        timestamp=now(session)
        session.add(Message(case_id=case.id,direction='out',level=case.level,to='sandbox@example.invalid',from_='evaluator@example.invalid',subject='Simulated complaint',body_text='Simulated complaint; no email was sent.',message_id=f'<simulation-{uuid4()}>',sent_at=timestamp))
        from ..engine.deadlines import deadlines
        for kind,due in deadlines(timestamp).items():
            session.add(Deadline(case_id=case.id,kind=kind,due_at=due))
        case.status=CaseStatus.WAITING
        case.facts_json={**case.facts_json,'owner_controlled':False,'sandbox_test':True}
        session.add(case)
        session.add(Event(case_id=case.id,actor='user',type='sent',title='Simulated complaint started',reason='Local evaluation only; no email was sent.',payload_json={'simulated':True}))
        session.commit()
    await request.app.state.events.publish('case_changed',{'case_id':data.case_id})
    return {'status':'simulation_started','sent':False}

@router.post('/inject')
async def inject(data: CaseInput,request: Request) -> dict:
    enabled()
    with Session(request.app.state.engine) as session:
        case=session.get(Case,data.case_id)
        if not case or case.company_id!='shopkart': raise HTTPException(422,'Injection is only available for ShopKart demo cases')
        messages=session.exec(select(Message).where(Message.case_id==case.id,Message.direction=='out').order_by(Message.sent_at)).all()
        if not messages: raise HTTPException(409,'Approve and send the complaint first')
        count=len(session.exec(select(Message).where(Message.case_id==case.id,Message.direction=='in')).all())
        if data.text and request.app.state.config.send_enabled: raise HTTPException(403,'Custom simulated replies require SEND_ENABLED=false')
        if count>=3 and not data.text: raise HTTPException(409,'All scripted replies already injected')
        last=messages[-1]
        payload=dict(case_id=case.id,message_id=f'<demo-{uuid4()}>',sender=last.to,subject='Re: '+last.subject,body=data.text.strip() if data.text and data.text.strip() else REPLIES[count].format(amount=case.amount_inr),in_reply_to=last.message_id)
    payload['simulated']=True
    await receive(request.app,payload)
    return {'status':'injected'}

@router.post('/reset')
async def reset(request: Request) -> dict:
    enabled()
    with Session(request.app.state.engine) as session:
        ids=[c.id for c in session.exec(select(Case)).all() if c.facts_json.get('demo_sample') or c.facts_json.get('verification_paused')]
        settings=session.get(Settings,1);settings.demo_clock_offset_seconds=0;session.add(settings);session.commit()
    from ..privacy import delete_cases
    delete_cases(request.app.state.engine, ids)
    return {'status':'reset','cases_deleted':len(ids)}

@router.get('/settings')
def demo_settings(request: Request) -> dict:
    return {'demo_mode':request.app.state.config.demo_mode}

@router.post('/warm')
async def warm(request: Request) -> dict:
    enabled()
    from .cases import sample
    case=await sample(request,'shopkart')
    from .drafts import draft
    await draft(case['id'],request)
    return {'status':'warmed','case_id':case['id']}
