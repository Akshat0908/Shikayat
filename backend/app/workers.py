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

async def act(app, session: Session, case: Case, analysis: ReplyAnalysis | None = None, breached: bool = False) -> None:
    deflections=sum(m.classification_json.get('category')=='deflection' for m in session.exec(select(Message).where(Message.case_id==case.id,Message.direction=='in')).all())
    decision=decide(case.level.value,analysis.category if analysis else 'acknowledged',deflections,breached,analysis.offered_amount_inr if analysis else None,case.amount_inr,bool(case.facts_json.get('missing_info')))
    event=Event(case_id=case.id,actor='ai',type='decision',title=decision.action,reason=decision.reason,payload_json={'action':decision.action,'level':decision.level})
    session.add(event)
    if decision.action=='confirm_receipt': case.status=CaseStatus.AWAITING_RECEIPT
    elif decision.action=='ask_user': case.status=CaseStatus.NEEDS_INFO
    elif decision.action in ('followup','escalate','counter','reply_info','prepare_filing'):
        case.level=Level(decision.level)
        messages=session.exec(select(Message).where(Message.case_id==case.id).order_by(Message.sent_at)).all()
        draft=await draft_escalation(case.facts_json,[{'date':m.sent_at.isoformat(),'body':m.body_text} for m in messages],decision.reason,(now(session)+timedelta(days=2)).date().isoformat())
        session.add(Event(case_id=case.id,actor='ai',type='draft',title='Next action drafted',reason=decision.reason,payload_json=draft.model_dump()))
        company=next((c for c in load_companies() if c['id']==case.company_id),None)
        contact=company['nodal_officer' if case.level==Level.L3 else 'grievance_officer'] if company else {}
        allowlist={s.strip().casefold() for s in get_settings().autopilot_allowlist.split(',') if s.strip()}
        if decision.action!='prepare_filing' and company and company.get('demo') and contact.get('email') and contact['email'].casefold() in allowlist:
            previous=next((m for m in reversed(messages) if m.direction=='out'),None)
            message_id=await send_email(contact,draft.subject,draft.body,False,True,previous.message_id if previous else None,[m.message_id for m in messages if m.message_id])
            session.add(Message(case_id=case.id,direction='out',level=case.level,to=contact['email'],from_=get_settings().user_email,subject=draft.subject,body_text=draft.body,message_id=message_id,sent_at=now(session)))
            case.status=CaseStatus.ESCALATED if decision.action=='escalate' else CaseStatus.WAITING
        else:
            case.status=CaseStatus.AWAITING_APPROVAL
    session.add(case);session.commit()
    await app.state.events.publish('decision',{'case_id':case.id,'action':decision.action,'reason':decision.reason})

async def receive(app, data: dict) -> None:
    with Session(app.state.engine) as session:
        if session.exec(select(Message).where(Message.message_id==data['message_id'])).first(): return
        case=session.get(Case,data['case_id'])
        if not case or case.status==CaseStatus.RESOLVED: return
        analysis=await classify_reply(data['body'])
        session.add(Message(case_id=case.id,direction='in',level=case.level,to=get_settings().user_email,from_=data['sender'],subject=data['subject'],body_text=data['body'],message_id=data['message_id'],in_reply_to=data.get('in_reply_to'),classification_json=analysis.model_dump(),sent_at=now(session)))
        session.add(Event(case_id=case.id,actor='company',type='reply',title=analysis.category,reason=analysis.summary_hinglish))
        if analysis.category in ('acknowledged','info_requested','resolution_offered'):
            for deadline in session.exec(select(Deadline).where(Deadline.case_id==case.id,Deadline.kind=='ack_48h',Deadline.status=='running')).all():
                deadline.status='met';session.add(deadline)
        session.commit()
        await act(app,session,case,analysis)

async def inbox_loop(app) -> None:
    while True:
        config=get_settings()
        if config.user_email and config.user_email_app_password.get_secret_value():
            try:
                def fetch() -> list[dict]:
                    with Session(app.state.engine) as session: return poll(session)
                for data in await asyncio.to_thread(fetch): await receive(app,data)
            except Exception:
                logger.error('{"worker":"inbox","status":"failed"}')
        await asyncio.sleep(5)

async def deadline_loop(app) -> None:
    while True:
        try:
            with Session(app.state.engine) as session:
                for deadline in session.exec(select(Deadline).where(Deadline.status=='running')).all():
                    if deadline.due_at.replace(tzinfo=timezone.utc)<=now(session):
                        deadline.status='breached';session.add(deadline);session.commit()
                        case=session.get(Case,deadline.case_id)
                        if case and case.status not in (CaseStatus.RESOLVED,CaseStatus.AWAITING_APPROVAL) and deadline.kind=='ack_48h': await act(app,session,case,breached=True)
        except Exception:
            logger.error('{"worker":"deadlines","status":"failed"}')
        await asyncio.sleep(10)
