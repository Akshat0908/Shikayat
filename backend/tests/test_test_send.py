from fastapi.testclient import TestClient
from sqlmodel import Session,select
from backend.app.ai.draft_complaint import EmailDraft
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Event,Message,Deadline


def test_test_send_only_uses_demo_inbox_and_tracks_case(tmp_path,monkeypatch):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',demo_company_email='demo@example.test',user_email='user@example.test',admin_passcode='test-owner'))
    sent=[]
    async def send(contact,subject,body,*args,**kwargs): sent.append((contact,subject,body));return '<test@example.test>'
    monkeypatch.setattr('backend.app.api.drafts.send_email',send)
    monkeypatch.setattr('backend.app.mail.threading_gmail.schedule_sent_lookup',lambda *args:None)
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[{'id':'leaf','name':'Leaf','sector':'e-commerce','grievance_officer':{'email':None,'verified':False}}])
    with TestClient(app,base_url='https://testserver') as client:
        assert client.post('/api/admin/login',json={'passcode':'test-owner'}).status_code==200
        with Session(app.state.engine) as session:
            case=Case(title='x',company_id='leaf',status=CaseStatus.AWAITING_APPROVAL,facts_json={'sample_scan_complete':True,'looks_like_sample':True});session.add(case);session.commit();session.refresh(case);case_id=case.id
            draft=EmailDraft(subject='Replacement',body='Please replace.',cited_refs=[],attachments=[],demand='replacement',deadline_date='2026-12-21')
            session.add(Event(case_id=case_id,type='draft',actor='ai',title='draft',payload_json=draft.model_dump()));session.commit()
        r=client.post(f'/api/cases/{case_id}/test-send');assert r.status_code==200
        assert sent[0][0]['email']=='demo@example.test' and sent[0][1].startswith('[TEST — would go to Leaf]')
        with Session(app.state.engine) as session:
            case=session.get(Case,case_id)
            assert case.status==CaseStatus.WAITING and case.facts_json['sandbox_test']
            message=session.exec(select(Message)).one()
            assert message.message_id=='<test@example.test>' and message.to=='demo@example.test' and '[TEST' in message.subject
            assert len(session.exec(select(Deadline)).all())==2
            assert session.exec(select(Event).where(Event.type=='sent')).one().payload_json['sandbox_test']


def test_restore_old_preview_is_idempotent_and_does_not_send(tmp_path,monkeypatch):
    from datetime import datetime,timezone
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',demo_company_email='demo@example.test',user_email='user@example.test',admin_passcode='test-owner'))
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[{'id':'leaf','name':'Leaf','sector':'e-commerce','grievance_officer':{'verified':False}}])
    monkeypatch.setattr('backend.app.mail.threading_gmail.schedule_sent_lookup',lambda *args:None)
    with TestClient(app,base_url='https://testserver') as client:
        client.post('/api/admin/login',json={'passcode':'test-owner'})
        with Session(app.state.engine) as session:
            case=Case(title='x',company_id='leaf',status=CaseStatus.AWAITING_APPROVAL,facts_json={'purchase_channel':'brand_website'});session.add(case);session.commit();cid=case.id
            draft=EmailDraft(subject='Replacement',body='Please replace.',cited_refs=[],attachments=[],demand='replacement',deadline_date='2026-12-21')
            session.add(Event(case_id=cid,type='draft',actor='ai',title='draft',payload_json=draft.model_dump()))
            session.add(Event(case_id=cid,type='test_send',actor='user',title='old preview',payload_json={'message_id':'<old@example.test>'}));session.commit()
        assert client.post(f'/api/cases/{cid}/recover-preview').json()['status']=='tracking_restored'
        assert client.post(f'/api/cases/{cid}/recover-preview').json()['status']=='tracking_restored'
        with Session(app.state.engine) as session:
            assert session.get(Case,cid).status==CaseStatus.WAITING
            assert len(session.exec(select(Message)).all())==1 and len(session.exec(select(Deadline)).all())==2
            assert len(session.exec(select(Event).where(Event.type=='sent')).all())==1


def test_visitor_can_confirm_manual_sandbox_preview(tmp_path,monkeypatch):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',demo_company_email='demo@example.test',user_email='user@example.test',send_enabled=True))
    monkeypatch.setattr('backend.app.api.manual_send.load_companies',lambda:[{'id':'leaf','name':'Leaf','sector':'e-commerce','grievance_officer':{'email':None,'verified':False}}])
    with TestClient(app,base_url='https://testserver') as client:
        client.get('/api/session');owner=client.cookies.get('shikayat_visitor')
        with Session(app.state.engine) as session:
            case=Case(title='x',owner_id=owner,company_id='leaf',status=CaseStatus.AWAITING_APPROVAL,facts_json={'sample_scan_complete':True,'looks_like_sample':True});session.add(case);session.commit();cid=case.id
            draft=EmailDraft(subject='Replacement',body='Please replace.',cited_refs=[],attachments=[],demand='replacement',deadline_date='2026-12-21')
            session.add(Event(case_id=cid,type='draft',actor='ai',title='draft',payload_json=draft.model_dump()));session.commit()
        assert client.post(f'/api/cases/{cid}/preview-sent').json()['status']=='sandbox_tracking_started'
        with Session(app.state.engine) as session:
            case=session.get(Case,cid);assert case.status==CaseStatus.WAITING and case.facts_json['sandbox_test']
            message=session.exec(select(Message)).one();assert message.message_id is None and message.to=='demo@example.test'
            assert len(session.exec(select(Deadline)).all())==2
