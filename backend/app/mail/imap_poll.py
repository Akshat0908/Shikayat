"""Fetch unseen thread replies without marking unrelated personal mail read."""
from email.utils import parseaddr
from imap_tools import MailBox
from .gmail import search, raw_query, message_id
from sqlmodel import Session, select
from ..config import get_settings
from ..models import Message


def poll(engine) -> list[dict]:
    config=get_settings()
    with Session(engine) as session:
        outgoing=session.exec(select(Message).where(Message.direction=='out')).all()
        seen={m.message_id for m in session.exec(select(Message).where(Message.direction=='in')).all()}
    found=[]
    with MailBox('imap.gmail.com',timeout=30).login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
        senders={m.to for m in outgoing}
        criteria=raw_query() if not senders else 'X-GM-RAW "in:anywhere {'+' '.join('from:'+s for s in senders)+' from:mailer-daemon from:postmaster}"'
        for folder,mail in search(box,criteria):
            headers={k.lower():v for k,v in mail.headers.items()}
            refs=' '.join([*headers.get('references',()),*headers.get('in-reply-to',())])
            sender=parseaddr(mail.from_)[1].casefold()
            is_bounce=('mailer-daemon' in sender or sender.startswith('postmaster@') or any('delivery-status' in v.lower() for v in headers.get('content-type',())))
            thread=refs+' '+(mail.text or '')
            matched=next((m for m in outgoing if m.message_id and m.message_id in thread and (sender==m.to.casefold() or is_bounce)),None)
            if matched is None and not is_bounce:
                subject=mail.subject.removeprefix('Re: ').removeprefix('RE: ')
                candidates=[m for m in outgoing if m.subject==subject and m.to.casefold()==sender]
                ids={m.case_id for m in candidates}
                matched=candidates[-1] if len(ids)==1 else None
            if matched and message_id(mail) not in seen:
                found.append(dict(folder=folder,case_id=matched.case_id,message_id=message_id(mail),sender=sender,subject=mail.subject,body=mail.text,in_reply_to=matched.message_id,bounced=is_bounce))
    return found
