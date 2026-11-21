import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from imap_tools import MailBox, AND
from sqlmodel import Session, select
from ..config import get_settings
from ..models import Message, Event

REPLIES=[
 'We regret the inconvenience caused. Your concern has been forwarded to the concerned team and will be addressed at the earliest.',
 'Your concern remains with the concerned team. New ticket DEMO-T205. We will respond at the earliest.',
 'Refund of INR {amount} has been initiated. Reference RFN-DEMO-104. It will be credited in 5–7 working days.',
]

async def company_loop(app) -> None:
    config=get_settings()
    while True:
        if config.demo_mode and config.send_enabled and config.demo_company_email and config.demo_company_app_password.get_secret_value():
            try:
                def respond() -> None:
                    with MailBox('imap.gmail.com').login(config.demo_company_email,config.demo_company_app_password.get_secret_value()) as box, Session(app.state.engine) as session:
                        outgoing=session.exec(select(Message).where(Message.direction=='out',Message.to==config.demo_company_email)).all()
                        completed={e.payload_json.get('message_id') for e in session.exec(select(Event).where(Event.type=='bot_replied')).all()}
                        for mail in box.fetch(AND(seen=False),mark_seen=False,limit=100):
                            message=next((m for m in outgoing if m.message_id==mail.message_id and m.message_id not in completed),None)
                            if not message: continue
                            from ..models import Case
                            case=session.get(Case,message.case_id)
                            if not case or case.company_id!='shopkart': continue
                            from ..demo.clock import now
                            age=(now(session)-message.sent_at.replace(tzinfo=now(session).tzinfo)).total_seconds()
                            if age<config.demo_reply_delay_seconds: continue
                            prior=[m for m in outgoing if m.case_id==case.id and m.sent_at<=message.sent_at]
                            index=2 if message.level.value=='L3' else min(len(prior)-1,1)
                            reply=EmailMessage();reply['From']=config.demo_company_email;reply['To']=config.user_email
                            reply['Subject']='Re: '+message.subject;reply['Message-ID']=make_msgid()
                            reply['In-Reply-To']=message.message_id;reply['References']=message.message_id
                            reply.set_content(REPLIES[index].format(amount=case.amount_inr))
                            with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30) as smtp:
                                smtp.login(config.demo_company_email,config.demo_company_app_password.get_secret_value());smtp.send_message(reply)
                            session.add(Event(case_id=case.id,actor='company',type='bot_replied',title='Demo company replied',reason='Scripted demo response.',payload_json={'message_id':message.message_id}));session.commit()
                await asyncio.to_thread(respond)
            except Exception:
                import logging
                logging.getLogger(__name__).error('{"worker":"demo_bot","status":"failed"}')
        await asyncio.sleep(5)
