import asyncio
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from sqlalchemy import text
from sqlmodel import Session,select
from backend.app import workers
from backend.app.ai import client as llm
from backend.app.ai.schemas import CaseFacts
from backend.app.ai.classify_reply import ReplyAnalysis
from backend.app.ai.draft_complaint import EmailDraft
from backend.app.api import cases
from backend.app.config import Settings,ROOT
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Deadline,LlmCall


def test_pipeline_inbox_and_deadlines_concurrently(tmp_path: Path,monkeypatch,caplog):
    config=Settings(database_url=f'sqlite:///{tmp_path}/concurrent.db',model_rates_json='{"test":{"input":1,"output":1}}')
    monkeypatch.setattr(llm,'get_settings',lambda:config)
    facts=CaseFacts.model_validate_json((ROOT/'data/samples/shopkart/facts.json').read_text())
    async def paid_step(task):
        await asyncio.to_thread(llm.record,task,'test',10,10,1,False)
        await asyncio.sleep(.01)
    async def extract(*args):
        await paid_step('extract');return facts
    async def rationale(*args):
        await paid_step('rationale');return 'Evidence supports the demand.'
    async def classify(*args):
        await paid_step('classify')
        return ReplyAnalysis(reply_type='deflection',acknowledged=True,original_remedy='refund',promised_action=None,refund_confirmed=False,resolution_status='unresolved',evidence_quotes=[],next_action='wait',reason='test',category='deflection',ticket_id=None,promised_date=None,offered_amount_inr=None,requested_info=[],is_templated=True,templated_signals=[],summary_hinglish='No commitment',concrete_action=None)
    async def draft(*args):
        await paid_step('draft')
        return EmailDraft(subject='Refund',body='Please refund.',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21')
    monkeypatch.setattr(cases,'extract_case',extract)
    monkeypatch.setattr(cases,'rationale',rationale)
    monkeypatch.setattr(workers,'classify_reply',classify)
    monkeypatch.setattr(workers,'draft_escalation',draft)
    async def run():
        app=create_app(config)
        async with app.router.lifespan_context(app):
            with Session(app.state.engine) as session:
                incoming=Case(title='Incoming',company_id='shopkart',status=CaseStatus.WAITING)
                expired=Case(title='Expired',company_id='shopkart',status=CaseStatus.WAITING)
                session.add_all([incoming,expired]);session.commit();iid=incoming.id;eid=expired.id
                session.add(Deadline(case_id=eid,kind='ack_48h',due_at=datetime.now(timezone.utc)-timedelta(days=1)));session.commit()
            def poll(engine):
                with Session(engine) as session: assert session.get(Case,iid)
                return [dict(case_id=iid,message_id='<concurrent-in>',sender='demo@example.test',subject='Refund',body='No action')]
            monkeypatch.setattr(workers,'poll',poll)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as api:
                response,_,_=await asyncio.gather(api.post('/api/cases',data={'text':'My refund is delayed'}),workers.inbox_iteration(app),workers.deadline_iteration(app))
            assert response.status_code==200,response.text
            with Session(app.state.engine) as session:
                assert session.get(Case,iid).status==CaseStatus.AWAITING_APPROVAL
                assert session.get(Case,eid).status==CaseStatus.AWAITING_APPROVAL
                assert len(session.exec(select(LlmCall)).all())>=5
                assert session.exec(text('PRAGMA journal_mode')).one()[0]=='wal'
                assert session.exec(text('PRAGMA busy_timeout')).one()[0]==5000
    asyncio.run(run())
    assert 'database is locked' not in caplog.text
    assert 'telemetry write failed' not in caplog.text


def test_telemetry_retries_once_and_never_crashes(tmp_path: Path,monkeypatch):
    attempts=[]
    def fail(*args):
        attempts.append(1)
        raise RuntimeError('storage unavailable')
    monkeypatch.setattr(llm,'get_settings',lambda:Settings(model_rates_json='{"test":{"input":1,"output":1}}'))
    monkeypatch.setattr(llm,'build_engine',fail)
    monkeypatch.setattr(llm,'ROOT',tmp_path)
    llm.record('test','test',10,20,1,False)
    assert len(attempts)==2
    assert len(list((tmp_path/'var/llm_pending').glob('*.json')))==1
