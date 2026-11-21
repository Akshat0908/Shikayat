import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import Session,select
from backend.app.main import create_app
from backend.app.config import Settings
from backend.app.models import Case,Message,CaseStatus,Deadline
from datetime import datetime, timedelta, timezone
from backend.app.ai.classify_reply import ReplyAnalysis
from backend.app.ai.draft_complaint import EmailDraft
from backend.app import workers

def test_reply_flow(tmp_path: Path,monkeypatch) -> None:
    async def classify(text: str, *args) -> ReplyAnalysis:
        return ReplyAnalysis(reply_type='substantive_resolution' if text=='offer' else 'deflection',acknowledged=True,original_remedy='refund',promised_action=None,refund_confirmed=False,resolution_status='unresolved',evidence_quotes=[],next_action='wait',reason='test',category='resolution_offered' if text=='offer' else 'deflection',ticket_id=None,promised_date=None,offered_amount_inr=4299 if text=='offer' else None,requested_info=[],is_templated=text!='offer',templated_signals=[],summary_hinglish='Demo reply',concrete_action=None)
    async def draft(*args) -> EmailDraft:
        return EmailDraft(subject='Refund',body='Please refund.',cited_refs=[],attachments=[],demand='refund',deadline_date=args[-1])
    count=0
    async def send(*args) -> str:
        nonlocal count
        count+=1
        return f'<sent-{count}>'
    monkeypatch.setattr(workers,'classify_reply',classify)
    monkeypatch.setattr(workers,'draft_escalation',draft)
    monkeypatch.setattr(workers,'send_email',send)
    monkeypatch.setattr(workers,'get_settings',lambda:Settings(autopilot_allowlist='demo@example.test'))
    contact={'email':'demo@example.test','verified':True}
    monkeypatch.setattr(workers,'load_companies',lambda:[{'id':'shopkart','demo':True,'sector':'e-commerce','grievance_officer':contact,'nodal_officer':contact}])
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/flow.db'))
    with TestClient(app):
        with Session(app.state.engine) as session:
            case=Case(title='Refund',company_id='shopkart',amount_inr=4299,status=CaseStatus.WAITING);session.add(case);session.commit();id=case.id
            session.add(Deadline(case_id=id,kind='ack_48h',due_at=datetime.now(timezone.utc)+timedelta(days=2),status='running'));session.commit()
        for i,(body,expected) in enumerate([('stall',CaseStatus.WAITING),('stall',CaseStatus.ESCALATED),('offer',CaseStatus.AWAITING_RECEIPT)]):
            asyncio.run(workers.receive(app,dict(case_id=id,message_id=f'<reply-{i}>',sender='demo@example.test',subject='Refund',body=body)))
            with Session(app.state.engine) as session:
                assert session.get(Case,id).status==expected
                if i==0:
                    assert session.exec(select(Deadline).where(Deadline.case_id==id)).first().status=='met'
        assert count==2
