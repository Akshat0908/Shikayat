from types import SimpleNamespace
from backend.app.mail.threading_gmail import extract_message_ids,fetch_thread_id
from backend.app.mail.matching import match_candidate
from backend.app.models import Case,Message


def test_folded_message_headers_are_unfolded():
    assert extract_message_ids(['<abc@exam\r\n ple.test>'])==['<abc@example.test>']
    assert extract_message_ids(['<a@example.test>\r\n <b@example.test>'])==['<a@example.test>','<b@example.test>']


def test_gmail_thread_fetch_and_match():
    box=SimpleNamespace(client=SimpleNamespace(uid=lambda *args:('OK',[b'1 (UID 42 X-GM-THRID 18345678901234)'])))
    thread=fetch_thread_id(box,'42');assert thread=='18345678901234'
    c=Case(title='case');sent=Message(case_id=c.id,direction='out',to='demo@example.test',from_='user@gmail.com',subject='s',body_text='b',gmail_thread_id=thread)
    mail=SimpleNamespace(headers={},subject='',text='')
    assert match_candidate(c.id,mail,[sent],{},['example.test'],'demo@example.test','user@gmail.com',thread)=='thread_id'


def test_stale_reply_keeps_original_level_and_does_not_trigger_followup(tmp_path,monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    from sqlmodel import Session,select
    from backend.app import workers
    from backend.app.ai.classify_reply import ReplyAnalysis
    from backend.app.config import Settings
    from backend.app.main import create_app
    from backend.app.models import CaseStatus,Level,Event
    async def classify(*args): return ReplyAnalysis(reply_type='deflection',acknowledged=True,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='wait',reason='test',category='deflection')
    monkeypatch.setattr(workers,'classify_reply',classify)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/stale.db'))
    with TestClient(app):
        with Session(app.state.engine) as session:
            c=Case(title='case',status=CaseStatus.ESCALATED,level=Level.L3);session.add(c);session.commit();cid=c.id
        asyncio.run(workers.receive(app,{'case_id':cid,'message_id':'<late>','sender':'care@example.test','subject':'reply','body':'late','reply_level':'L2'}))
        with Session(app.state.engine) as session:
            assert session.exec(select(Message).where(Message.case_id==cid)).first().level==Level.L2
            assert session.exec(select(Event).where(Event.case_id==cid,Event.type=='late_reply')).first()
            assert not session.exec(select(Event).where(Event.case_id==cid,Event.type=='decision')).all()
