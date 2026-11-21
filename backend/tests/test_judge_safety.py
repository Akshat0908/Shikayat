import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import Session,select
import pytest
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Level,Message,Evidence,Event
from backend.app.engine.policy import decide
from backend.app.engine.send_guard import guard
from backend.app.mail.smtp_send import send_email
from backend.app.ai.classify_reply import ReplyAnalysis
from backend.app import workers


def test_policy_ack_followup_and_limits():
    assert decide('L2','acknowledged',ack_breached=True).action=='followup'
    assert decide('L2','acknowledged',ack_breached=True,followups=1).action=='escalate'
    assert decide('L2','deflection',deflections=2).level=='L3'
    assert decide('L3','deflection',deflections=2).action=='prepare_filing'
    assert decide('L2','deflection',redress_breached=True).action=='escalate'
    assert decide('L2','deflection',outbound_count=8).action=='prepare_filing'
    assert decide('L2','deflection',bounced=True).action=='prepare_filing'
    assert decide('L2','deflection',paused=True).action=='wait'


def test_send_guard_spacing_and_per_level_limits():
    t=datetime(2026,11,21,tzinfo=timezone.utc)
    config=Settings(demo_mode=False,min_outbound_interval_hours=72)
    case=Case(title='case',level=Level.L2)
    def msg(level=Level.L2): return Message(case_id=case.id,direction='out',level=level,to='a',from_='b',subject='s',body_text='b',sent_at=t)
    assert guard(case,[msg()],t+timedelta(hours=71),config,False)[1]==t+timedelta(hours=72)
    assert guard(case,[msg()]*4,t+timedelta(hours=73),config,False)[0]=='Follow-up limit reached at this level.'
    case.level=Level.L3
    assert guard(case,[msg(Level.L3)]*3,t+timedelta(hours=73),config,False)[0]=='Follow-up limit reached at this level.'
    case.facts_json={'paused':True}
    assert 'paused' in guard(case,[],t,config,False)[0].lower()
    case.facts_json={'recipient_bounced':True}
    assert 'bounced' in guard(case,[],t,config,False)[0].lower()


def test_public_demo_blocks_approved_real_contact(monkeypatch):
    monkeypatch.setattr('backend.app.mail.smtp_send.get_settings',lambda:Settings(public_demo=True,autopilot_allowlist='demo@example.test',send_enabled=True))
    with pytest.raises(ValueError,match='Sending disabled on the public demo'):
        asyncio.run(send_email({'email':'real@example.test','verified':True},'subject','body',True,False))
    with pytest.raises(ValueError,match='Sending disabled on the public demo'):
        asyncio.run(send_email({'email':'demo@example.test','verified':True},'subject','body',True,False))


def test_pause_report_resume_and_delete(tmp_path,monkeypatch):
    async def classify(*args):
        return ReplyAnalysis(reply_type='acknowledgment',acknowledged=True,original_remedy='Refund of ₹100',promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='Wait',reason='Reported call',category='acknowledged')
    monkeypatch.setattr(workers,'classify_reply',classify)
    monkeypatch.setattr('backend.app.api.case_controls.ROOT',tmp_path)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db.sqlite'))
    with TestClient(app) as client:
        with Session(app.state.engine) as s:
            case=Case(title='case',status=CaseStatus.WAITING);s.add(case);s.commit();cid=case.id
            folder=tmp_path/'var'/'evidence'/cid;folder.mkdir(parents=True);path=folder/'image.png';path.write_bytes(b'fixture')
            s.add(Evidence(case_id=cid,kind='screenshot',path=str(path)));s.commit()
        assert client.post(f'/api/cases/{cid}/pause').json()['paused']
        assert client.post(f'/api/cases/{cid}/update',json={'text':'They called and said five days'}).status_code==200
        with Session(app.state.engine) as s:
            assert s.get(Case,cid).facts_json['pending_review']['acknowledged']
            assert s.exec(select(Event).where(Event.case_id==cid,Event.type=='reply')).first().payload_json['origin']=='user-reported'
        assert client.post(f'/api/cases/{cid}/resume').json()['paused'] is False
        assert client.delete(f'/api/cases/{cid}').status_code==200
        assert not path.exists()
        with Session(app.state.engine) as s:
            assert s.get(Case,cid) is None
            assert not s.exec(select(Message).where(Message.case_id==cid)).all()
            assert not s.exec(select(Evidence).where(Evidence.case_id==cid)).all()


def test_bounce_records_evidence_and_stops_sending(tmp_path,monkeypatch):
    async def fake_draft(facts,thread,reason,deadline):
        from backend.app.ai.draft_complaint import EmailDraft
        return EmailDraft(subject='NCH',body='Please review.',cited_refs=[],attachments=[],demand='refund',deadline_date=deadline)
    monkeypatch.setattr(workers,'draft_escalation',fake_draft)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db.sqlite'))
    with TestClient(app):
        with Session(app.state.engine) as s:
            c=Case(title='case',company_id='shopkart',status=CaseStatus.WAITING);s.add(c);s.commit();cid=c.id
        asyncio.run(workers.receive(app,{'case_id':cid,'message_id':'<bounce>','sender':'mailer-daemon@example.test','subject':'Delivery failed','body':'Delivery failed','bounced':True}))
        with Session(app.state.engine) as s:
            assert s.get(Case,cid).facts_json['recipient_bounced']
            assert s.get(Case,cid).level==Level.L4
            assert s.exec(select(Evidence).where(Evidence.case_id==cid,Evidence.kind=='email')).first()
            assert s.exec(select(Event).where(Event.case_id==cid,Event.type=='nch_pack')).first()


def test_bounce_matching_uses_thread_id(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from backend.app.mail import imap_poll
    from backend.app.db import build_engine,init_db
    engine=build_engine(f'sqlite:///{tmp_path}/imap.db');init_db(engine)
    with Session(engine) as s:
        case=Case(title='case');s.add(case);s.commit()
        s.add(Message(case_id=case.id,direction='out',to='company@example.test',from_='user@example.test',subject='Grievance',body_text='complaint',message_id='<outbound-123>'));s.commit()
    mail=SimpleNamespace(headers={'in-reply-to':['<outbound-123>']},from_='MAILER-DAEMON@example.test',subject='Delivery failed',text='Delivery failed',obj={'Message-ID':'<bounce-123>'})
    class Box:
        def __init__(self,*args,**kwargs): pass
        def login(self,*args): return self
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr(imap_poll,'MailBox',Box)
    monkeypatch.setattr(imap_poll,'search',lambda *args:[('All Mail',mail)])
    result=imap_poll.poll(engine)
    assert len(result)==1 and result[0]['bounced'] and result[0]['in_reply_to']=='<outbound-123>'


def test_paused_and_public_demo_never_reach_smtp(tmp_path,monkeypatch):
    from backend.app.ai.draft_complaint import EmailDraft
    from backend.app.models import Event
    sent=[]
    async def fake_send(*args): sent.append(args);return '<sent>'
    monkeypatch.setattr('backend.app.api.drafts.send_email',fake_send)
    monkeypatch.setattr('backend.app.api.drafts.load_companies',lambda:[{'id':'real','demo':False,'sector':'e-commerce','grievance_officer':{'email':'real@example.test','verified':True}}])
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/api.db',public_demo=True,autopilot_allowlist='demo@example.test'))
    with TestClient(app) as client:
        with Session(app.state.engine) as s:
            c=Case(title='Case',company_id='real',status=CaseStatus.AWAITING_APPROVAL);s.add(c);s.commit();cid=c.id
            draft=EmailDraft(subject='Test',body='Test',cited_refs=[],attachments=[],demand='',deadline_date='2026-12-21')
            s.add(Event(case_id=cid,actor='ai',type='draft',title='Draft',payload_json=draft.model_dump()));s.commit()
        assert client.post(f'/api/cases/{cid}/approve').status_code==409
        assert client.get(f'/api/cases/{cid}/board').json()['sending_disabled'] is True
        assert sent==[]
        assert client.post(f'/api/cases/{cid}/pause').status_code==200
        assert client.post(f'/api/cases/{cid}/approve').status_code==409
        assert sent==[]


def test_deferred_followup_sends_after_demo_clock_advances(tmp_path,monkeypatch):
    from backend.app.ai.draft_complaint import EmailDraft
    from backend.app.models import Settings as DbSettings
    async def fake_draft(facts,thread,reason,deadline):
        return EmailDraft(subject='Follow-up',body='Please review.',cited_refs=[],attachments=[],demand='refund',deadline_date=deadline)
    sent=[]
    async def fake_send(*args): sent.append(args);return '<followup>'
    monkeypatch.setattr(workers,'draft_escalation',fake_draft)
    monkeypatch.setattr(workers,'send_email',fake_send)
    contact={'email':'demo@example.test','verified':True}
    monkeypatch.setattr(workers,'load_companies',lambda:[{'id':'shopkart','demo':True,'sector':'e-commerce','grievance_officer':contact,'nodal_officer':contact}])
    config=Settings(database_url=f'sqlite:///{tmp_path}/deferred.db',demo_mode=True,demo_outbound_interval_seconds=30,autopilot_allowlist='demo@example.test')
    app=create_app(config)
    with TestClient(app):
        with Session(app.state.engine) as s:
            c=Case(title='case',company_id='shopkart',status=CaseStatus.WAITING,facts_json={'demo_sample':True});s.add(c);s.commit();cid=c.id
            s.add(Message(case_id=cid,direction='out',to='demo@example.test',from_='user@example.test',subject='s',body_text='b',message_id='<sent>',sent_at=datetime.now(timezone.utc)));s.commit()
        analysis=ReplyAnalysis(reply_type='deflection',acknowledged=True,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='',reason='',category='deflection')
        asyncio.run(workers.act(app,cid,analysis))
        with Session(app.state.engine) as s:
            assert s.get(Case,cid).facts_json.get('pending_action') and not sent
            setting=s.get(DbSettings,1);setting.demo_clock_offset_seconds=40;s.add(setting);s.commit()
        asyncio.run(workers.deadline_iteration(app))
        with Session(app.state.engine) as s:
            assert len(sent)==1 and 'pending_action' not in s.get(Case,cid).facts_json


def test_permanent_smtp_block_prepares_nch_without_server_details(tmp_path):
    import smtplib
    from backend.app.mail.delivery import permanently_blocked,record_blocked
    from backend.app.db import build_engine,init_db
    engine=build_engine(f'sqlite:///{tmp_path}/blocked.db');init_db(engine)
    with Session(engine) as s:
        c=Case(title='Refund case',status=CaseStatus.WAITING);s.add(c);s.commit();cid=c.id
    assert permanently_blocked(smtplib.SMTPRecipientsRefused({'x@example.test':(550,b'blocked')}))
    assert not permanently_blocked(smtplib.SMTPRecipientsRefused({'x@example.test':(450,b'temporary')}))
    record_blocked(engine,cid)
    with Session(engine) as s:
        case=s.get(Case,cid)
        assert case.level==Level.L4 and case.facts_json['recipient_bounced']
        assert s.exec(select(Event).where(Event.case_id==cid,Event.type=='nch_pack')).first()


def test_deferred_escalation_keeps_level_until_send(tmp_path,monkeypatch):
    from backend.app.ai.draft_complaint import EmailDraft
    from backend.app.models import Settings as DbSettings
    async def fake_draft(facts,thread,reason,deadline):
        return EmailDraft(subject='Escalation',body='Please review.',cited_refs=[],attachments=[],demand='refund',deadline_date=deadline)
    sent=[]
    async def fake_send(*args): sent.append(args);return '<escalation>'
    monkeypatch.setattr(workers,'draft_escalation',fake_draft);monkeypatch.setattr(workers,'send_email',fake_send)
    contact={'email':'demo@example.test','verified':True}
    monkeypatch.setattr(workers,'load_companies',lambda:[{'id':'shopkart','demo':True,'sector':'e-commerce','grievance_officer':contact,'nodal_officer':contact}])
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/escalation.db',demo_mode=True,demo_outbound_interval_seconds=30,autopilot_allowlist='demo@example.test'))
    with TestClient(app):
        with Session(app.state.engine) as s:
            c=Case(title='case',company_id='shopkart',status=CaseStatus.WAITING,facts_json={'demo_sample':True});s.add(c);s.commit();cid=c.id
            s.add(Message(case_id=cid,direction='out',to='demo@example.test',from_='user@example.test',subject='s',body_text='b',message_id='<sent>',sent_at=datetime.now(timezone.utc)))
            for i in range(2): s.add(Message(case_id=cid,direction='in',to='user@example.test',from_='demo@example.test',subject='s',body_text='b',message_id=f'<reply{i}>',classification_json={'category':'deflection'}))
            s.commit()
        analysis=ReplyAnalysis(reply_type='deflection',acknowledged=True,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='',reason='',category='deflection')
        asyncio.run(workers.act(app,cid,analysis))
        with Session(app.state.engine) as s:
            assert s.get(Case,cid).level==Level.L2 and not sent
            setting=s.get(DbSettings,1);setting.demo_clock_offset_seconds=40;s.add(setting);s.commit()
        asyncio.run(workers.deadline_iteration(app))
        with Session(app.state.engine) as s:
            assert s.get(Case,cid).level==Level.L3 and len(sent)==1
