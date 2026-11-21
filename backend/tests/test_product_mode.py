import asyncio
from datetime import datetime, timezone
from urllib.parse import parse_qs,urlparse
from fastapi.testclient import TestClient
from sqlmodel import Session,select
from backend.app.ai.classify_reply import ReplyAnalysis
from backend.app.ai.draft_complaint import EmailDraft
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Event,Message,Deadline,UserProfile
from backend.app import workers


def test_owner_session_guards_direct_sending_and_tools(tmp_path,monkeypatch):
    config=Settings(database_url=f'sqlite:///{tmp_path}/db',admin_passcode='owner-secret',public_demo=True,user_email='tracking@example.test',send_enabled=True)
    company={'id':'merchant','name':'Merchant','sector':'e-commerce','demo':False,'grievance_officer':{'email':'officer@example.test','verified':True}}
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[company]);monkeypatch.setattr('backend.app.api.manual_send.load_companies',lambda:[company])
    sent=[]
    async def send(*args,**kwargs):sent.append(args);return '<sent@example.test>'
    monkeypatch.setattr('backend.app.api.drafts.send_email',send)
    app=create_app(config)
    with TestClient(app,base_url='https://testserver') as client:
        client.get('/api/session'); visitor=client.cookies.get('shikayat_visitor')
        with Session(app.state.engine) as session:
            case=Case(title='A case',company_id='merchant',status=CaseStatus.AWAITING_APPROVAL,facts_json={'sample_scan_complete':True});session.add(case);session.commit();session.refresh(case);cid=case.id
            session.add(Event(case_id=cid,actor='ai',type='draft',title='Draft',payload_json=EmailDraft(subject='Refund',body='Please refund.',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21').model_dump()));session.add(UserProfile(name='Owner Name',phone='01234567890',email='private@example.test'));session.commit()
        assert client.get('/api/admin/session').json()['admin'] is False
        assert client.get('/api/profile').status_code==403
        assert client.post(f'/api/cases/{cid}/approve').status_code==404
        for route in ('clock','inject','reset','warm'): assert client.post('/api/demo/'+route,json={'case_id':cid}).status_code==403
        assert client.post('/api/admin/login',json={'passcode':'wrong'}).status_code==403
        assert client.post('/api/admin/login',json={'passcode':'owner-secret'}).status_code==200
        assert client.get('/api/admin/session').json()['admin'] is True
        session_cookie=client.cookies.get('shikayat_admin')
        assert client.post(f'/api/cases/{cid}/confirm-recipient').status_code==200
        assert client.post(f'/api/cases/{cid}/approve').status_code==200 and len(sent)==1
        with Session(app.state.engine) as session: assert session.get(Case,cid).facts_json['owner_controlled'] is True
        assert client.post('/api/admin/logout').status_code==200
        assert client.get('/api/admin/session').json()['admin'] is False
        assert client.get('/api/admin/session',headers={'Cookie':f'shikayat_admin={session_cookie}'}).json()['admin'] is False
        assert client.post(f'/api/cases/{cid}/approve').status_code==404


def test_visitor_manual_compose_public_mode_and_confirm(tmp_path,monkeypatch):
    config=Settings(database_url=f'sqlite:///{tmp_path}/db',public_demo=True,user_email='tracking@example.test',send_enabled=True)
    company={'id':'merchant','name':'Merchant','sector':'e-commerce','demo':False,'grievance_officer':{'email':'officer@example.test','verified':True}}
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[company]);monkeypatch.setattr('backend.app.api.manual_send.load_companies',lambda:[company])
    app=create_app(config)
    with TestClient(app,base_url='https://testserver') as client:
        client.get('/api/session'); visitor=client.cookies.get('shikayat_visitor')
        with Session(app.state.engine) as session:
            c=Case(owner_id=visitor,title='Case',company_id='merchant',status=CaseStatus.AWAITING_APPROVAL,facts_json={'sample_scan_complete':True});session.add(c);session.commit();session.refresh(c);cid=c.id
            draft=EmailDraft(subject='Refund',body='Please refund.\n\nSincerely,\nOwner Name\nprivate@example.test',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21')
            session.add(Event(case_id=cid,actor='ai',type='draft',title='Draft',payload_json=draft.model_dump()));session.commit()
        assert client.post(f'/api/cases/{cid}/manual-compose').status_code==409
        assert client.post(f'/api/cases/{cid}/confirm-recipient').status_code==200
        result=client.post(f'/api/cases/{cid}/manual-compose');assert result.status_code==200
        data=result.json();parts=urlparse(data['mailto']);query=parse_qs(parts.query)
        assert parts.path=='officer@example.test' and query['cc']==[data['tracking_address']]
        assert '[Shikayat #' in query['subject'][0] and 'private@example.test' not in query['body'][0]
        assert 'reply all' in data['note']
        with Session(app.state.engine) as s: assert not s.exec(select(Deadline)).all()
        assert client.post(f'/api/cases/{cid}/manual-sent').json()['status']=='sent_by_user'
        with Session(app.state.engine) as s:
            assert len(s.exec(select(Deadline)).all())==2
            assert s.exec(select(Message)).one().from_=='User’s email app'


def test_visitor_sample_preview_uses_sandbox_only(tmp_path,monkeypatch):
    config=Settings(database_url=f'sqlite:///{tmp_path}/db',public_demo=True,user_email='tracking@example.test',demo_company_email='sandbox@example.test',send_enabled=True)
    monkeypatch.setattr('backend.app.api.manual_send.load_companies',lambda:[{'id':'m','name':'Merchant','grievance_officer':{'email':None,'verified':False}}])
    app=create_app(config)
    with TestClient(app,base_url='https://testserver') as client:
        client.get('/api/session'); visitor=client.cookies.get('shikayat_visitor')
        with Session(app.state.engine) as s:
            case=Case(owner_id=visitor,title='Case',company_id='m',status=CaseStatus.AWAITING_APPROVAL,facts_json={'looks_like_sample':True,'sample_scan_complete':True});s.add(case);s.commit();s.refresh(case);cid=case.id
            s.add(Event(case_id=cid,actor='ai',type='draft',title='Draft',payload_json=EmailDraft(subject='Test',body='Please review.',cited_refs=[],attachments=[],demand='other',deadline_date='2026-12-21').model_dump()));s.commit()
        assert client.post(f'/api/cases/{cid}/test-send').status_code==403
        result=client.post(f'/api/cases/{cid}/preview-compose');assert result.status_code==200
        parsed=urlparse(result.json()['mailto']);query=parse_qs(parsed.query)
        assert parsed.path=='sandbox@example.test' and query['subject'][0].startswith('[TEST — would go to Merchant]')
        assert client.post(f'/api/cases/{cid}/manual-compose').status_code in (409,422)
        with Session(app.state.engine) as s: assert not s.exec(select(Message)).all() and not s.exec(select(Deadline)).all()


def test_visitor_case_never_autosends(tmp_path,monkeypatch):
    config=Settings(database_url=f'sqlite:///{tmp_path}/db',demo_mode=True,demo_outbound_interval_seconds=0,autopilot_allowlist='sandbox@example.test')
    company={'id':'shopkart','demo':True,'sector':'e-commerce','grievance_officer':{'email':'sandbox@example.test','verified':True}}
    monkeypatch.setattr(workers,'load_companies',lambda:[company]);sent=[]
    async def send(*args):sent.append(args);return '<sent>'
    async def draft(facts,thread,reason,deadline):return EmailDraft(subject='Follow up',body='Please reply.',cited_refs=[],attachments=[],demand='refund',deadline_date=deadline)
    monkeypatch.setattr(workers,'send_email',send);monkeypatch.setattr(workers,'draft_escalation',draft)
    app=create_app(config)
    with TestClient(app,base_url='https://testserver'):
        with Session(app.state.engine) as s:
            c=Case(title='Case',company_id='shopkart',status=CaseStatus.WAITING,facts_json={'sample_scan_complete':True,'owner_controlled':False});s.add(c);s.commit();s.refresh(c);cid=c.id
        analysis=ReplyAnalysis(reply_type='deflection',acknowledged=True,original_remedy='Refund',promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='Follow up',reason='No concrete reply',category='deflection')
        asyncio.run(workers.act(app,cid,analysis))
        with Session(app.state.engine) as s: assert s.get(Case,cid).status==CaseStatus.AWAITING_APPROVAL
        assert sent==[]


def test_company_directory_labels_sandbox_without_exposing_mailbox(tmp_path,monkeypatch):
    from backend.app.api import companies
    monkeypatch.setattr(companies,'load_companies',lambda:[{'id':'shopkart','name':'ShopKart','demo':True,'grievance_officer':{'verified':True,'email':'private@example.test'}},{'id':'real','name':'Real Company','demo':False,'grievance_officer':{'verified':False,'email':None}}])
    with TestClient(create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',user_email='',demo_company_email=''))) as client:
        data=client.get('/api/companies').json()
        assert data[0]['sandbox'] and data[1]['sandbox'] is False
        assert 'private@example.test' not in str(data)


def test_owner_still_cannot_send_paused_or_sample_evidence(tmp_path,monkeypatch):
    config=Settings(database_url=f'sqlite:///{tmp_path}/db',admin_passcode='owner-secret',public_demo=True,user_email='owner@example.test',send_enabled=True)
    company={'id':'m','name':'Merchant','sector':'e-commerce','demo':False,'grievance_officer':{'email':'officer@example.test','verified':True}}
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[company]);sent=[]
    async def send(*args,**kwargs):sent.append(args);return '<sent>'
    monkeypatch.setattr('backend.app.api.drafts.send_email',send)
    app=create_app(config)
    with TestClient(app,base_url='https://testserver') as client:
        client.get('/api/session'); visitor=client.cookies.get('shikayat_visitor')
        assert client.post('/api/admin/login',json={'passcode':'owner-secret'}).status_code==200
        with Session(app.state.engine) as s:
            cases=[]
            for facts in ({'paused':True,'sample_scan_complete':True},{'looks_like_sample':True,'sample_scan_complete':True}):
                c=Case(title='Case',company_id='m',status=CaseStatus.AWAITING_APPROVAL,facts_json=facts);s.add(c);s.commit();s.refresh(c);cases.append(c.id)
                s.add(Event(case_id=c.id,actor='ai',type='draft',title='Draft',payload_json=EmailDraft(subject='Refund',body='Please refund.',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21').model_dump()));s.commit()
        for cid in cases:
            assert client.post(f'/api/cases/{cid}/approve').status_code==409
        assert sent==[]
