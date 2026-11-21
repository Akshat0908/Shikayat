"""Fetch only server-side filtered case candidates; never scan the whole mailbox."""
import logging
from email.utils import parseaddr
from imap_tools import MailBox
from sqlmodel import Session, select
from .gmail import search, message_id
from .matching import match_candidate,sender_authentication,verified_domains
from .tracking import plus_address
from ..config import get_settings
from ..engine.company import load_companies
from ..models import Case, Event, Message

logger=logging.getLogger(__name__)


def queries(case: Case, sent: list[Message], company: dict, user_email: str, demo_address: str) -> list[str]:
    if not sent: return []
    result=[]
    try:
        address=plus_address(user_email,case.id)
        result.append(f'OR TO "{address}" CC "{address}"')
    except ValueError: pass
    for message in sent:
        if message.message_id and all(c not in message.message_id for c in '\r\n"'):
            result.extend([f'HEADER In-Reply-To "{message.message_id}"',f'HEADER References "{message.message_id}"'])
    domains=verified_domains(company,demo_address)
    earliest=min(m.sent_at for m in sent)
    after=int(earliest.timestamp())
    senders=[demo_address] if company.get('demo') and demo_address else domains
    for sender in senders:
        if sender and all(c.isalnum() or c in '@.-_' for c in sender):
            result.append(f'X-GM-RAW "in:anywhere from:{sender} after:{after}"')
    return list(dict.fromkeys(result))


def apply_label(box, mail) -> None:
    try:
        names={f.name for f in box.folder.list()}
        if 'Shikayat' not in names: box.folder.create('Shikayat')
        status,_=box.client.uid('STORE',mail.uid,'+X-GM-LABELS','("Shikayat")')
        if status!='OK': raise RuntimeError('Label rejected')
    except Exception:
        logger.warning('Unable to apply Shikayat label')


def poll(engine) -> list[dict]:
    config=get_settings()
    companies={c['id']:c for c in load_companies()}
    with Session(engine) as session:
        cases=session.exec(select(Case)).all()
        outgoing=session.exec(select(Message).where(Message.direction=='out')).all()
        seen={m.message_id for m in session.exec(select(Message).where(Message.direction=='in')).all()}
        for event in session.exec(select(Event).where(Event.type=='candidate_pending')).all(): seen.add(event.payload_json.get('message_id'))
        work=[]
        for case in cases:
            sent=[m for m in outgoing if m.case_id==case.id]
            company=companies.get(case.company_id)
            if not sent or not company: continue
            work.append((case,sent,company,queries(case,sent,company,config.user_email,config.demo_company_email)))
    if not any(query for _,_,_,query in work): return []
    found=[];candidates={}; examined=set()
    ranks={'thread':0,'plus address':1,'case tag':2,'ticket ID':3,'order ID':4,'domain only':5}
    with MailBox('imap.gmail.com',timeout=30).login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
        for case,sent,company,criteria in work:
            domains=verified_domains(company,config.demo_company_email)
            for query in criteria:
                for folder,mail in search(box,query,readonly=False):
                    mid=message_id(mail)
                    if not mid or mid in seen or (mid,case.id) in examined: continue
                    examined.add((mid,case.id))
                    sender=parseaddr(mail.from_)[1].casefold()
                    if sender==config.user_email.casefold(): continue
                    headers={k.lower():v for k,v in mail.headers.items()}
                    bounce=('mailer-daemon' in sender or sender.startswith('postmaster@') or any('delivery-status' in v.lower() for v in headers.get('content-type',())))
                    match=match_candidate(case.id,mail,sent,case.facts_json,domains,sender,config.user_email)
                    if not match or (bounce and match!='thread'): continue
                    if company.get('demo') and sender!=config.demo_company_email.casefold() and not bounce:
                        verified,detail=False,'Sender does not match the configured demo address.'
                    else: verified,detail=sender_authentication(list(headers.get('authentication-results',())),sender,domains)
                    if bounce: verified=False;detail='Delivery status notification needs user confirmation.'
                    data=dict(folder=folder,case_id=case.id,message_id=mid,sender=sender,subject=mail.subject,body=mail.text or '',in_reply_to=next((m.message_id for m in reversed(sent) if m.message_id),None),bounced=bounce,match_method=match,sender_verified=verified,verification_detail=detail,needs_confirmation=match=='domain only' or not verified,uid=str(mail.uid))
                    previous=candidates.get(mid)
                    rank=ranks[match]
                    if previous is None or rank<previous[0]: candidates[mid]=(rank,[data])
                    elif rank==previous[0]: previous[1].append(data)
        for _,items in candidates.values():
            ambiguous=len(items)>1
            for data in items:
                if ambiguous: data['needs_confirmation']=True;data['verification_detail']+=' Multiple cases match; user review required.'
                found.append(data)
                if not data['needs_confirmation']:
                    box.folder.set(data['folder'],readonly=False)
                    from types import SimpleNamespace
                    apply_label(box,SimpleNamespace(uid=data['uid']))

    return found


def label_confirmed(folder: str,uid: str) -> None:
    from types import SimpleNamespace
    config=get_settings()
    with MailBox('imap.gmail.com',timeout=30).login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
        box.folder.set(folder,readonly=False)
        apply_label(box,SimpleNamespace(uid=uid))
