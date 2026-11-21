"""Gmail special-use folder discovery and read-only, cross-folder searches."""
from collections.abc import Iterator
import json
import logging
import time
import threading
import socket
from ..config import ROOT

logger=logging.getLogger(__name__)
from imap_tools import MailBox
from imap_tools.message import MailMessage


def message_id(mail: MailMessage) -> str:
    return str(mail.obj.get('Message-ID','')).strip()


def folders(box: MailBox) -> list[str]:
    listing=box.folder.list()
    names=[]
    for flag in ('\\All','\\Junk'):
        names.extend(f.name for f in listing if flag.casefold() in {s.casefold() for s in f.flags})
    if not names:
        names=['INBOX']
    return list(dict.fromkeys(names))


def raw_query(message_id: str | None = None, subject: str | None = None, sender: str | None = None) -> str:
    terms=[]
    if message_id: terms.append('rfc822msgid:'+message_id.strip('<>'))
    if subject: terms.append('subject:"'+subject.replace('"','')+'"')
    query='in:anywhere '+ ('{'+ ' '.join(terms)+'}' if len(terms)>1 else ' '.join(terms))
    if sender: query+=' from:'+sender
    return 'X-GM-RAW "'+query.replace('\\','\\\\').replace('"','\\"')+'"'


def search(box: MailBox, criteria: str, limit: int = 100, readonly: bool = True) -> Iterator[tuple[str,MailMessage]]:
    seen=set()
    for folder in folders(box):
        started=time.monotonic();count=0;error=None;messages=[]
        connection=getattr(getattr(box,'client',None),'sock',None)
        def interrupt() -> None:
            try: connection.shutdown(socket.SHUT_RDWR)
            except (OSError,AttributeError): pass
        timer=threading.Timer(10,interrupt) if connection is not None else None
        if timer: timer.daemon=True;timer.start()
        try:
            box.folder.set(folder,readonly=readonly)
            messages=list(box.fetch(criteria,mark_seen=False,reverse=True,limit=limit,bulk=True))
            count=len(messages)
        except Exception as exc:
            error=type(exc).__name__
            raise
        finally:
            if timer: timer.cancel()
            entry={'folder':folder,'query':criteria,'elapsed_ms':round((time.monotonic()-started)*1000,1),'count':count,'error':error}
            line=json.dumps(entry,ensure_ascii=False)
            logger.info('imap_search %s',line)
            try:
                path=ROOT/'var'/'verification'/'imap_queries.log';path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('a',encoding='utf-8') as stream: stream.write(line+'\n')
            except OSError: logger.warning('Could not write IMAP query log')
        for mail in messages:
            id=message_id(mail)
            if not id or id in seen: continue
            seen.add(id)
            yield folder,mail



def locate(box: MailBox, message_id: str, subject: str) -> list[str]:
    """Report every selected special folder containing this exact test message."""
    found=[]
    for folder in folders(box):
        box.folder.set(folder,readonly=True)
        for mail in box.fetch(raw_query(message_id,subject),mark_seen=False,reverse=True,limit=20,bulk=True):
            if str(mail.obj.get('Message-ID','')).strip('<>')==message_id.strip('<>') or mail.subject==subject:
                found.append(folder);break
    return found
