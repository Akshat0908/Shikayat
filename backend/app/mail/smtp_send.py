import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from ..config import get_settings

async def send_email(recipient: dict, subject: str, body: str, approved: bool, demo: bool, in_reply_to: str | None = None, references: list[str] | None = None) -> str:
    config=get_settings()
    address=recipient.get('email')
    allowlist={s.strip().casefold() for s in config.autopilot_allowlist.split(',') if s.strip()}
    if not config.send_enabled:
        raise ValueError('Sending disabled; no message sent')
    if not address or not recipient.get('verified'):
        raise ValueError('Verify recipient contact before sending')
    if not approved and not (demo and address.casefold() in allowlist):
        raise ValueError('User approval required')
    if not config.user_email or not config.user_email_app_password.get_secret_value():
        raise ValueError('Sender mailbox credentials are missing')
    message=EmailMessage()
    message['From']=config.user_email;message['To']=address;message['Subject']=subject
    message['Message-ID']=make_msgid()
    if in_reply_to:
        message['In-Reply-To']=in_reply_to
        message['References']=' '.join([*(references or []),in_reply_to])
    message.set_content(body)
    def deliver() -> None:
        with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30) as smtp:
            smtp.login(config.user_email,config.user_email_app_password.get_secret_value())
            smtp.send_message(message)
    await asyncio.to_thread(deliver)
    return str(message['Message-ID'])
