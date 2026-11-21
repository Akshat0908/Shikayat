from fastapi.testclient import TestClient
from sqlmodel import Session,select
from backend.app.ai.draft_complaint import EmailDraft
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Event,Message,Deadline


def test_test_send_only_uses_demo_inbox_and_never_changes_case(tmp_path,monkeypatch):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',demo_company_email='demo@example.test',user_email='user@example.test',admin_passcode='test-owner'))
    sent=[]
    async def send(contact,subject,body,*args,**kwargs): sent.append((contact,subject,body));return '<test@example.test>'
    monkeypatch.setattr('backend.app.api.drafts.send_email',send)
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[{'id':'leaf','name':'Leaf','grievance_officer':{'email':None,'verified':False}}])
    with TestClient(app,base_url='https://testserver') as client:
        assert client.post('/api/admin/login',json={'passcode':'test-owner'}).status_code==200
        with Session(app.state.engine) as session:
            case=Case(title='x',company_id='leaf',status=CaseStatus.AWAITING_APPROVAL,facts_json={'sample_scan_complete':True,'looks_like_sample':True});session.add(case);session.commit();session.refresh(case);case_id=case.id
            draft=EmailDraft(subject='Replacement',body='Please replace.',cited_refs=[],attachments=[],demand='replacement',deadline_date='2026-12-21')
            session.add(Event(case_id=case_id,type='draft',actor='ai',title='draft',payload_json=draft.model_dump()));session.commit()
        r=client.post(f'/api/cases/{case_id}/test-send');assert r.status_code==200
        assert sent[0][0]['email']=='demo@example.test' and sent[0][1].startswith('[TEST — would go to Leaf]')
        with Session(app.state.engine) as session:
            assert session.get(Case,case_id).status==CaseStatus.AWAITING_APPROVAL
            assert not session.exec(select(Message)).all() and not session.exec(select(Deadline)).all()
            assert session.exec(select(Event).where(Event.type=='test_send')).one().payload_json['simulated']
