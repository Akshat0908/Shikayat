from urllib.parse import parse_qs,urlparse
from fastapi.testclient import TestClient
from sqlmodel import Session,select
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Event,Message,Deadline
from backend.app.ai.draft_complaint import EmailDraft


def test_manual_compose_and_explicit_confirmation(tmp_path,monkeypatch):
    config=Settings(database_url=f'sqlite:///{tmp_path}/manual.db',user_email='user@example.test',send_enabled=True)
    company={'id':'merchant','sector':'e-commerce','demo':False,'grievance_officer':{'email':'officer@example.test','verified':True}}
    monkeypatch.setattr('backend.app.api.manual_send.load_companies',lambda:[company])
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[company])
    app=create_app(config)
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            case=Case(title='Case',company_id='merchant',status=CaseStatus.AWAITING_APPROVAL);session.add(case);session.commit();cid=case.id
            draft=EmailDraft(subject='Refund',body='Please refund.',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21')
            session.add(Event(case_id=cid,actor='ai',type='draft',title='Draft',payload_json=draft.model_dump()));session.commit()
        assert client.post(f'/api/cases/{cid}/manual-compose').status_code==409
        assert client.post(f'/api/cases/{cid}/confirm-recipient').status_code==200
        response=client.post(f'/api/cases/{cid}/manual-compose');assert response.status_code==200
        payload=response.json(); query=parse_qs(urlparse(payload['mailto']).query)
        assert query['cc']==[payload['tracking_address']] and '[Shikayat #' in query['subject'][0]
        assert parse_qs(urlparse(payload['gmail']).query)['cc']==[payload['tracking_address']]
        with Session(app.state.engine) as session:
            assert session.get(Case,cid).status==CaseStatus.AWAITING_APPROVAL
            assert not session.exec(select(Deadline).where(Deadline.case_id==cid)).all()
        assert client.post(f'/api/cases/{cid}/manual-sent').json()['status']=='sent_by_user'
        assert client.post(f'/api/cases/{cid}/manual-sent').status_code==409
        with Session(app.state.engine) as session:
            assert session.get(Case,cid).status==CaseStatus.WAITING
            assert len(session.exec(select(Deadline).where(Deadline.case_id==cid)).all())==2
            assert session.exec(select(Message).where(Message.case_id==cid)).first().message_id is None
