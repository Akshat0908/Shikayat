"""Gmail thread metadata; every lookup is scoped to a known message ID."""
import asyncio
import logging
import re
from imap_tools import MailBox
from sqlmodel import Session,select
from .gmail import message_id,raw_query,search
from ..config import get_settings
from ..models import Message

logger=logging.getLogger(__name__)
_inflight: set[str]=set()


def extract_message_ids(values) -> list[str]:
    """Unfold headers before extracting actual RFC Message-ID tokens."""
    text=' '.join(str(v) for v in values)
    return [re.sub(r'\s+','',match) for match in re.findall(r'<[^<>]+>',text)]


def fetch_thread_id(box, uid: str) -> str | None:
    status,records=box.client.uid('FETCH',uid,'(X-GM-THRID)')
    if status!='OK': return None
    for record in records:
        value=record[0] if isinstance(record,tuple) else record
        if isinstance(value,bytes):
            found=re.search(rb'X-GM-THRID\s+(\d+)',value,re.I)
            if found: return found.group(1).decode('ascii')
    return None


def sent_thread_lookup(engine, message_id_value: str) -> None:
    config=get_settings()
    try:
        with MailBox('imap.gmail.com',timeout=10).login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
            for _,mail in search(box,raw_query(message_id=message_id_value)):
                if message_id(mail)!=message_id_value: continue
                thread_id=fetch_thread_id(box,str(mail.uid))
                if thread_id:
                    with Session(engine) as session:
                        row=session.exec(select(Message).where(Message.message_id==message_id_value,Message.direction=='out')).first()
                        if row: row.gmail_thread_id=thread_id;session.add(row);session.commit()
                break
    except Exception as error:
        logger.warning('Sent thread lookup skipped: %s',type(error).__name__)


def schedule_sent_lookup(engine, message_id_value: str) -> None:
    if message_id_value in _inflight: return
    _inflight.add(message_id_value)
    async def run() -> None:
        try: await asyncio.to_thread(sent_thread_lookup,engine,message_id_value)
        finally: _inflight.discard(message_id_value)
    asyncio.create_task(run())
