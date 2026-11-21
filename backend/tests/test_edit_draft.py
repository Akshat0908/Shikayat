from fastapi.testclient import TestClient
from sqlmodel import Session, select
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case, CaseStatus, Event
from backend.app.ai.draft_complaint import EmailDraft


def test_edit_draft_persists_and_approval_sends_saved_body(tmp_path, monkeypatch):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/test.db'))
    sent=[]
    async def send(contact,subject,body,*args):
        sent.append(body)
        return '<test-message>'
    monkeypatch.setattr('backend.app.api.drafts.send_email',send)
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[{'id':'shopkart','demo':True,'grievance_officer':{'email':'demo@example.test','verified':True}}])
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            case=Case(title='Refund',company_id='shopkart',status=CaseStatus.AWAITING_APPROVAL)
            session.add(case);session.commit();case_id=case.id
            original=EmailDraft(subject='Refund',body='Original',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21')
            session.add(Event(case_id=case_id,actor='ai',type='draft',title='Draft',reason='Prepared',payload_json=original.model_dump()));session.commit()
        saved=client.patch(f'/api/cases/{case_id}/draft',json={'body':'Edited complaint'}).json()['body']
        assert 'Edited complaint' in saved
        assert client.post(f'/api/cases/{case_id}/draft').json()['body']==saved
        assert client.post(f'/api/cases/{case_id}/approve').status_code==409
        assert client.post(f'/api/cases/{case_id}/confirm-recipient').status_code==200
        assert client.post(f'/api/cases/{case_id}/approve').status_code==200
        assert sent==[saved]
        assert client.patch(f'/api/cases/{case_id}/draft',json={'body':'Late edit'}).status_code==409
        with Session(app.state.engine) as session:
            assert session.exec(select(Event).where(Event.case_id==case_id,Event.title=='Complaint edited')).first()
