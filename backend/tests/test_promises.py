from datetime import datetime, timezone
from backend.app.engine.promises import promise_from_reply


def test_working_days_skip_weekends():
    fri=datetime(2026,11,20,12,tzinfo=timezone.utc)
    p=promise_from_reply('We will refund within 3 working days.',None,fri,None)
    assert p and p.promised_date.isoformat()=='2026-11-25' and p.grace_until.date().isoformat()=='2026-11-26'

def test_promise_within_and_beyond_redress():
    now=datetime(2026,11,20,tzinfo=timezone.utc); due=datetime(2026,12,20,tzinfo=timezone.utc)
    assert not promise_from_reply('We will refund by 2026-12-01.','2026-12-01',now,due).exceeds_redress
    assert promise_from_reply('We will refund by 2026-12-25.','2026-12-25',now,due).exceeds_redress

def test_vague_or_unsubstantiated_dates_are_not_promises():
    now=datetime(2026,11,20,tzinfo=timezone.utc)
    assert promise_from_reply('We will resolve this soon.',None,now,None) is None
    assert promise_from_reply('We will refund soon.','2026-11-25',now,None) is None


def test_promise_flow_uses_demo_clock_and_quotes_followup(tmp_path,monkeypatch):
    import asyncio
    from datetime import timedelta
    from fastapi.testclient import TestClient
    from sqlmodel import Session,select
    from backend.app import workers
    from backend.app.ai.classify_reply import ReplyAnalysis
    from backend.app.ai.draft_complaint import EmailDraft
    from backend.app.config import Settings
    from backend.app.main import create_app
    from backend.app.models import Case,CaseStatus,Deadline,Message,Settings as DbSettings
    from backend.app.demo.clock import now
    sent=[]
    async def classify(*args): return ReplyAnalysis(reply_type='acknowledgment',acknowledged=True,original_remedy='Refund',promised_action='Refund',refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='Wait',reason='Promise',category='acknowledged')
    async def draft(facts,thread,reason,deadline): return EmailDraft(subject='Follow-up',body='Please review.',cited_refs=[],attachments=[],demand='refund',deadline_date=deadline)
    async def send(*args): sent.append(args);return '<followup>'
    monkeypatch.setattr(workers,'classify_reply',classify);monkeypatch.setattr(workers,'draft_escalation',draft);monkeypatch.setattr(workers,'send_email',send)
    contact={'email':'demo@example.test','verified':True}
    monkeypatch.setattr(workers,'load_companies',lambda:[{'id':'shopkart','demo':True,'sector':'e-commerce','grievance_officer':contact,'nodal_officer':contact}])
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/promise.db',demo_mode=True,demo_outbound_interval_seconds=0,autopilot_allowlist='demo@example.test'))
    with TestClient(app):
        with Session(app.state.engine) as s:
            clock=now(s);c=Case(title='Refund',company_id='shopkart',status=CaseStatus.WAITING,facts_json={'demo_sample':True});s.add(c);s.commit();cid=c.id
            s.add(Message(case_id=cid,direction='out',to='demo@example.test',from_='user@example.test',subject='Refund',body_text='Refund',message_id='<sent>',sent_at=clock))
            s.add(Deadline(case_id=cid,kind='resolve_30d',due_at=clock+timedelta(days=30)));s.commit()
        text='We will refund within 3 working days.'
        asyncio.run(workers.receive(app,{'case_id':cid,'message_id':'<reply>','sender':'demo@example.test','subject':'Re: Refund','body':text}))
        with Session(app.state.engine) as s:
            case=s.get(Case,cid);promise=case.facts_json['promise'];assert not sent
            item=s.exec(select(Deadline).where(Deadline.case_id==cid,Deadline.kind=='promise')).first();assert item
            setting=s.get(DbSettings,1);setting.demo_clock_offset_seconds=int((item.due_at.replace(tzinfo=timezone.utc)-datetime.now(timezone.utc)).total_seconds())+10;s.add(setting);s.commit()
        asyncio.run(workers.deadline_iteration(app))
        assert len(sent)==1 and text in sent[0][2]


def test_promise_guard_waits_or_pushes_back_until_redress():
    from backend.app.config import Settings
    from backend.app.engine.send_guard import guard
    from backend.app.models import Case
    now=datetime(2026,11,20,tzinfo=timezone.utc)
    case=Case(title='case',facts_json={'promise':{'grace_until':'2026-11-26T23:59:59+00:00','exceeds_redress':False}})
    assert guard(case,[],now,Settings(),False)[1].date().isoformat()=='2026-11-26'
    case.facts_json={'promise':{'grace_until':'2027-01-01T23:59:59+00:00','redress_at':'2026-12-20T00:00:00+00:00','exceeds_redress':True,'pushback_sent':False}}
    assert guard(case,[],now,Settings(),False)==(None,None)
    case.facts_json['promise']['pushback_sent']=True
    assert guard(case,[],now,Settings(),False)[1].date().isoformat()=='2026-12-20'


def test_vague_refund_promise_is_deflection():
    from backend.app.ai.classify_reply import ReplyAnalysis,enforce_forensics
    text='We acknowledge your complaint and will refund you soon.'
    analysis=ReplyAnalysis(reply_type='acknowledgment',acknowledged=True,original_remedy=None,promised_action='will refund you soon',refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='wait',reason='test',concrete_action='will refund you soon')
    assert enforce_forensics(analysis,text,4299,'refund').reply_type=='deflection'
