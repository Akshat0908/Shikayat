"""Fetch unseen thread replies without marking unrelated personal mail read."""
from email.utils import parseaddr
from imap_tools import MailBox, AND
from sqlmodel import Session, select
from ..config import get_settings
from ..models import Message


def poll(session: Session) -> list[dict]:
    config=get_settings()
    outgoing=session.exec(select(Message).where(Message.direction=='out')).all()
    seen={m.message_id for m in session.exec(select(Message).where(Message.direction=='in')).all()}
    found=[]
    with MailBox('imap.gmail.com').login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
        for mail in box.fetch(AND(seen=False),mark_seen=False,limit=100):
            headers={k.lower():v for k,v in mail.headers.items()}
            refs=' '.join(headers.get('references',())+headers.get('in-reply-to',()))
            sender=parseaddr(mail.from_)[1].casefold()
            matched=next((m for m in outgoing if m.message_id and m.message_id in refs and sender==m.to.casefold()),None)
            if matched is None:
                subject=mail.subject.removeprefix('Re: ').removeprefix('RE: ')
                candidates=[m for m in outgoing if m.subject==subject and m.to.casefold()==sender]
                ids={m.case_id for m in candidates}
                matched=candidates[-1] if len(ids)==1 else None
            if matched and mail.message_id not in seen:
                found.append(dict(case_id=matched.case_id,message_id=mail.message_id,sender=sender,subject=mail.subject,body=mail.text,in_reply_to=matched.message_id))
    return found
