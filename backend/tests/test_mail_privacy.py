from datetime import datetime,timezone
from email.message import EmailMessage
from types import SimpleNamespace
from backend.app.mail.matching import sender_authentication,match_candidate,verified_domains
from backend.app.mail.imap_poll import queries
from backend.app.mail.tracking import plus_address,case_tag,tracked_subject
from backend.app.models import Case,Message


def test_search_is_case_restricted_and_no_messages_means_no_query():
    c=Case(title='Case',company_id='merchant');company={'verified_domains':['example.test']}
    assert queries(c,[],company,'user@gmail.com','')==[]
    m=Message(case_id=c.id,direction='out',to='care@example.test',from_='user@gmail.com',subject='s',body_text='b',message_id='<abc>',sent_at=datetime(2026,11,1,tzinfo=timezone.utc))
    result=queries(c,[m],company,'user@gmail.com','')
    assert result and all(('TO ' in q or 'CC ' in q or 'X-GM-THRID ' in q or ('from:example.test' in q and 'after:' in q)) for q in result)
    assert plus_address('user@gmail.com',c.id) in result[0]
    assert all('HEADER ' not in q for q in result)
    m.gmail_thread_id='123456789'
    assert 'X-GM-THRID 123456789' in queries(c,[m],company,'user@gmail.com','')
    assert '[Shikayat #' in tracked_subject('Subject',c.id)


def test_authentication_requires_google_authserv_and_aligned_pass():
    domains=['example.test'];sender='care@example.test'
    assert sender_authentication(['mx.google.com; dkim=pass header.d=example.test'],sender,domains)[0]
    assert sender_authentication(['mx.google.com; spf=pass smtp.mailfrom=care@example.test'],sender,domains)[0]
    assert not sender_authentication(['attacker.test; dkim=pass header.d=example.test'],sender,domains)[0]
    assert not sender_authentication(['mx.google.com; dkim=pass header.d=other.test'],sender,domains)[0]
    assert not sender_authentication(['mx.google.com; dkim=pass header.d=example.test'],'evil@other.test',domains)[0]


def test_matching_ladder_and_domain_only():
    c=Case(title='Case');m=Message(case_id=c.id,direction='out',to='care@example.test',from_='user@gmail.com',subject='s',body_text='b',message_id='<abc>')
    mail=SimpleNamespace(headers={'in-reply-to':['<abc>']},subject='',text='')
    assert match_candidate(c.id,mail,[m],{},['example.test'],'care@example.test','user@gmail.com')=='in_reply_to'
    mail.headers={'to':[plus_address('user@gmail.com',c.id)]}
    assert match_candidate(c.id,mail,[m],{},['example.test'],'care@example.test','user@gmail.com')=='plus_address'
    mail.headers={};mail.subject=case_tag(c.id)
    assert match_candidate(c.id,mail,[m],{},['example.test'],'care@example.test','user@gmail.com')=='case_tag'
    mail.subject='';mail.text='Ticket T1234'
    assert match_candidate(c.id,mail,[m],{'known_ticket_ids':['T1234']},['example.test'],'care@example.test','user@gmail.com')=='ticket_id'
    mail.text='Order O1234'
    assert match_candidate(c.id,mail,[m],{'order_id':'O1234'},['example.test'],'care@example.test','user@gmail.com')=='order_id'
    assert match_candidate(c.id,mail,[m],{},['example.test'],'care@example.test','user@gmail.com')=='domain_only'
    assert match_candidate(c.id,mail,[m],{},['example.test'],'evil@other.test','user@gmail.com') is None
    assert verified_domains({'demo':True},'demo@gmail.com')==['gmail.com']


def test_unverified_mail_waits_for_user_confirmation(tmp_path,monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    from sqlmodel import Session,select
    from backend.app.main import create_app
    from backend.app.config import Settings
    from backend.app.models import Event,Message,CaseStatus
    from backend.app import workers
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db.sqlite'))
    classified=[]
    async def classify(*args): classified.append(True);raise AssertionError('Unverified mail must not be classified')
    monkeypatch.setattr(workers,'classify_reply',classify)
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            case=Case(title='Case',status=CaseStatus.WAITING);session.add(case);session.commit();cid=case.id
        data={'case_id':cid,'message_id':'<incoming>','sender':'unknown@example.test','subject':'Reply','body':'message','sender_verified':False,'needs_confirmation':True,'match_method':'thread'}
        asyncio.run(workers.receive(app,data))
        with Session(app.state.engine) as session:
            pending=session.exec(select(Event).where(Event.case_id==cid,Event.type=='candidate_pending')).first()
            assert pending and pending.title=='Unverified sender'
            assert not session.exec(select(Message).where(Message.case_id==cid)).all()
            event_id=pending.id
        assert not classified
        assert client.post(f'/api/cases/{cid}/candidates/{event_id}',json={'accept':False}).status_code==200
        assert not classified


def test_empty_inbox_work_does_not_connect(tmp_path,monkeypatch):
    from backend.app.mail import imap_poll
    from backend.app.db import build_engine,init_db
    engine=build_engine(f'sqlite:///{tmp_path}/empty.db');init_db(engine)
    def forbidden(*args,**kwargs): raise AssertionError('Must not connect without restricted work')
    monkeypatch.setattr(imap_poll,'MailBox',forbidden)
    assert imap_poll.poll(engine)==[]


def test_forged_later_authentication_result_is_not_trusted():
    headers=['mx.google.com; dkim=fail header.d=example.test','mx.google.com; dkim=pass header.d=example.test']
    assert not sender_authentication(headers,'care@example.test',['example.test'])[0]


def test_outbound_message_has_case_tag_and_reply_to(monkeypatch):
    import asyncio
    from pydantic import SecretStr
    from backend.app.config import Settings
    from backend.app.mail import smtp_send
    captured=[]
    class SMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def login(self,*args): pass
        def send_message(self,message): captured.append(message)
    monkeypatch.setattr(smtp_send,'get_settings',lambda:Settings(user_email='user@gmail.com',user_email_app_password=SecretStr('test'),send_enabled=True))
    monkeypatch.setattr(smtp_send.smtplib,'SMTP_SSL',SMTP)
    case_id='12345678-0000-0000-0000-000000000000'
    asyncio.run(smtp_send.send_email({'email':'care@example.test','verified':True},'Refund','Body',True,False,None,None,case_id))
    assert captured[0]['Reply-To']=='user+shk12345678@gmail.com'
    assert '[Shikayat #12345678]' in captured[0]['Subject']


def test_shikayat_label_is_verified():
    from backend.app.mail.imap_poll import apply_label
    class Client:
        def uid(self,command,uid,*args):
            if command=='STORE': return 'OK',[b'']
            return 'OK',[b'1 (X-GM-LABELS ("Shikayat"))']
    box=SimpleNamespace(client=Client(),folder=SimpleNamespace(list=lambda:[SimpleNamespace(name='Shikayat')]))
    assert apply_label(box,SimpleNamespace(uid='17')) is True


def test_plus_match_returns_before_slow_header_search(tmp_path,monkeypatch):
    from backend.app.mail import imap_poll
    from backend.app.db import build_engine,init_db
    from backend.app.config import Settings
    from sqlmodel import Session
    engine=build_engine(f'sqlite:///{tmp_path}/early.db');init_db(engine)
    with Session(engine) as s:
        case=Case(title='Case',company_id='shopkart');s.add(case);s.commit();cid=case.id
        s.add(Message(case_id=cid,direction='out',to='demo@gmail.com',from_='user@gmail.com',subject='s',body_text='b',message_id='<sent>'));s.commit()
    headers={'to':[plus_address('user@gmail.com',cid)],'in-reply-to':['<sent>'],'authentication-results':['mx.google.com; dkim=pass header.d=gmail.com']}
    mail=SimpleNamespace(headers=headers,from_='demo@gmail.com',subject='Re: s',text='Reply',uid='17',obj={'Message-ID':'<reply>'})
    class Box:
        def __init__(self,*args,**kwargs): self.folder=SimpleNamespace(set=lambda *a,**k:None)
        def login(self,*args): return self
        def __enter__(self): return self
        def __exit__(self,*args): pass
    calls=[]
    def search(_box,query,**kwargs):
        calls.append(query)
        if len(calls)>1: raise AssertionError('A later search must not discard a definitive reply')
        return [('All Mail',mail)]
    monkeypatch.setattr(imap_poll,'get_settings',lambda:Settings(user_email='user@gmail.com',demo_company_email='demo@gmail.com'))
    monkeypatch.setattr(imap_poll,'load_companies',lambda:[{'id':'shopkart','demo':True}])
    monkeypatch.setattr(imap_poll,'MailBox',Box);monkeypatch.setattr(imap_poll,'search',search)
    monkeypatch.setattr(imap_poll,'label_confirmed',lambda *args:True)
    result=imap_poll.poll(engine)
    assert len(calls)==1 and result[0]['sender_verified'] and result[0]['label_applied']
