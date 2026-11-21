"""Gmail special-use folder discovery and read-only, cross-folder searches."""
from collections.abc import Iterator
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
        box.folder.set(folder,readonly=readonly)
        for mail in box.fetch(criteria,mark_seen=False,reverse=True,limit=limit,bulk=True):
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
