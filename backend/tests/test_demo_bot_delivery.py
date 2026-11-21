import pytest
from types import SimpleNamespace
from pydantic import SecretStr
from sqlmodel import Session,select
from backend.app.config import Settings
from backend.app.db import build_engine,init_db
from backend.app.demo import company_bot
from backend.app.models import Case,CaseStatus,Event,Message
from backend.app.mail.tracking import plus_address


def test_bot_records_send_before_imap_logout_failure(tmp_path,monkeypatch):
    engine=build_engine(f'sqlite:///{tmp_path}/bot.db');init_db(engine)
    config=Settings(user_email='user@gmail.com',demo_company_email='demo@gmail.com',demo_company_app_password=SecretStr('test'),demo_reply_delay_seconds=0)
    with Session(engine) as session:
        case=Case(title='case',company_id='shopkart',status=CaseStatus.WAITING);session.add(case);session.commit();cid=case.id
        session.add(Message(case_id=cid,direction='out',to='demo@gmail.com',from_='user@gmail.com',subject='Case',body_text='Body',message_id='<sent@gmail.com>'));session.commit()
    mail=SimpleNamespace(obj={'Message-ID':'<sent@gmail.com>','Reply-To':plus_address('user@gmail.com',cid)})
    class Box:
        def __init__(self,*args,**kwargs): pass
        def login(self,*args): return self
        def __enter__(self): return self
        def __exit__(self,*args): raise TimeoutError('logout failed')
    sent=[]
    class SMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def login(self,*args): pass
        def send_message(self,message): sent.append(message)
    monkeypatch.setattr(company_bot,'get_settings',lambda:config)
    monkeypatch.setattr(company_bot,'MailBox',Box);monkeypatch.setattr(company_bot,'search',lambda *args:[('All Mail',mail)])
    monkeypatch.setattr(company_bot.smtplib,'SMTP_SSL',SMTP)
    with pytest.raises(TimeoutError): company_bot.respond(engine)
    with Session(engine) as session:
        event=session.exec(select(Event).where(Event.case_id==cid,Event.type=='bot_replied')).first()
        assert event and event.payload_json['reply_to_plus']
    assert sent[0]['To']==plus_address('user@gmail.com',cid)
    assert company_bot.respond(engine)==[] and len(sent)==1
