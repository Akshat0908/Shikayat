import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from imap_tools import MailBox
from ..mail.gmail import search, raw_query, message_id
from sqlmodel import Session, select
from ..config import get_settings
from ..models import Message, Event
from ..mail.tracking import plus_address

REPLIES=[
 'We regret the inconvenience caused. Your concern has been forwarded to the concerned team and will be addressed at the earliest.',
 'Your concern remains with the concerned team. We will respond at the earliest.',
 'Refund of INR {amount} has been initiated. Reference RFN-DEMO-104. It will be credited in 5–7 working days.',
]

def respond(engine) -> list[Event]:
    config=get_settings()
    from ..models import Case, CaseStatus
    from ..demo.clock import now
    with Session(engine) as session:
        outgoing=session.exec(select(Message).where(Message.direction=='out',Message.to==config.demo_company_email)).all()
        completed={e.payload_json.get('message_id') for e in session.exec(select(Event).where(Event.type=='bot_replied')).all()}
        cases={c.id:c for c in session.exec(select(Case).where(Case.company_id=='shopkart')).all()}
        timestamp=now(session)
    events=[]
    eligible=[m for m in outgoing if m.message_id and m.message_id not in completed and m.case_id in cases and cases[m.case_id].status!=CaseStatus.RESOLVED and not cases[m.case_id].facts_json.get('verification_paused')]
    if not eligible: return events
    with MailBox('imap.gmail.com',timeout=10).login(config.demo_company_email,config.demo_company_app_password.get_secret_value()) as box:
        for message in eligible:
            case=cases[message.case_id]
            if (timestamp-message.sent_at.replace(tzinfo=timestamp.tzinfo)).total_seconds()<config.demo_reply_delay_seconds: continue
            for folder,mail in search(box,raw_query(message_id=message.message_id)):
                if message.message_id!=message_id(mail): continue
                prior=[m for m in outgoing if m.case_id==case.id and m.sent_at<=message.sent_at]
                index=2 if message.level.value=='L3' else min(len(prior)-1,1)
                expected=plus_address(config.user_email,case.id)
                reply_to=parseaddr(str(mail.obj.get('Reply-To','')))[1]
                target=reply_to if reply_to.casefold()==expected.casefold() else config.user_email
                reply=EmailMessage();reply['From']=config.demo_company_email;reply['To']=target
                reply['Subject']='Re: '+message.subject;reply['Message-ID']=make_msgid(domain=config.demo_company_email.rsplit('@',1)[-1])
                reply['In-Reply-To']=message.message_id;reply['References']=message.message_id
                reply.set_content(REPLIES[index].format(amount=case.amount_inr))
                with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30) as smtp:
                    smtp.login(config.demo_company_email,config.demo_company_app_password.get_secret_value());smtp.send_message(reply)
                event=Event(case_id=case.id,actor='company',type='bot_replied',title='Demo company replied',reason='Scripted demo response.',payload_json={'message_id':message.message_id,'folder':folder,'reply_to_plus':target.casefold()==expected.casefold()})
                # Persist before IMAP logout: a logout timeout must not cause a duplicate SMTP reply.
                with Session(engine) as session:
                    session.add(event);session.commit();session.refresh(event)
                events.append(event);completed.add(message.message_id)
                break

    return events


async def company_loop(app) -> None:
    config=app.state.config
    if not (config.demo_mode and config.send_enabled and config.demo_company_email and config.demo_company_app_password.get_secret_value()):
        import logging
        logging.getLogger(__name__).info('Demo bot disabled: Gmail credentials or sending not configured')
    while True:
        if config.demo_mode and config.send_enabled and config.demo_company_email and config.demo_company_app_password.get_secret_value():
            try:
                events=await asyncio.to_thread(respond,app.state.engine)
                case_ids=[event.case_id for event in events]
                for case_id in case_ids:
                    await app.state.events.publish('case_changed',{'case_id':case_id})
            except Exception as error:
                from ..workers import worker_failure
                worker_failure(app,'demo_bot',error)
        await asyncio.sleep(2)
