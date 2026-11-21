"""Fetch only server-side filtered case candidates; never scan the whole mailbox."""
import logging
import re
from email.utils import parseaddr
from imap_tools import MailBox
from sqlmodel import Session, select
from .gmail import search, message_id
from .matching import match_candidate,sender_authentication,verified_domains
from .tracking import plus_address
from .threading_gmail import fetch_thread_id
from ..config import get_settings
from ..engine.company import load_companies
from ..models import Case, CaseStatus, Event, Message

logger=logging.getLogger(__name__)


def queries(case: Case, sent: list[Message], company: dict, user_email: str, demo_address: str) -> list[str]:
    if not sent: return []
    result=[]
    try:
        address=plus_address(user_email,case.id)
        result.extend([f'TO "{address}"',f'CC "{address}"'])
    except ValueError: pass
    for thread_id in dict.fromkeys(m.gmail_thread_id for m in sent if m.gmail_thread_id):
        if thread_id.isdecimal(): result.append(f'X-GM-THRID {thread_id}')
    domains=verified_domains(company,demo_address)
    earliest=min(m.sent_at for m in sent)
    after=int(earliest.timestamp())
    senders=[demo_address] if company.get('demo') and demo_address else domains
    for sender in senders:
        if sender and all(c.isalnum() or c in '@.-_' for c in sender):
            result.append(f'X-GM-RAW "in:anywhere from:{sender} after:{after}"')
    return list(dict.fromkeys(result))


def apply_label(box, mail) -> bool:
    try:
        names={f.name for f in box.folder.list()}
        if 'Shikayat' not in names: box.folder.create('Shikayat')
        status,_=box.client.uid('STORE',mail.uid,'+X-GM-LABELS','("Shikayat")')
        if status!='OK': raise RuntimeError('Label rejected')
        status,records=box.client.uid('FETCH',mail.uid,'(X-GM-LABELS)')
        if status!='OK' or not any(b'shikayat' in item.lower() for item in records if isinstance(item,bytes)): raise RuntimeError('Label verification failed')
        return True
    except Exception:
        logger.warning('Unable to apply or verify Shikayat label')
        return False


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
            if case.status==CaseStatus.RESOLVED or case.facts_json.get('verification_paused'): continue
            sent=[m for m in outgoing if m.case_id==case.id]
            company=companies.get(case.company_id)
            if not sent or not company: continue
            work.append((case,sent,company,queries(case,sent,company,config.user_email,config.demo_company_email)))
    if not any(query for _,_,_,query in work): return []
    found=[];candidates={};examined=set();query_cache={}
    ranks={'thread_id':0,'in_reply_to':1,'plus_address':2,'case_tag':3,'ticket_id':4,'order_id':5,'domain_only':6}
    for case,sent,company,criteria in work:
        domains=verified_domains(company,config.demo_company_email)
        for query in criteria:
            if query not in query_cache:
                fetched=[]
                try:
                    with MailBox('imap.gmail.com',timeout=10).login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
                        for folder,mail in search(box,query,readonly=True):
                            try: thread_id=fetch_thread_id(box,str(mail.uid))
                            except Exception as error:
                                logger.warning('Thread metadata skipped: %s',type(error).__name__);thread_id=None
                            fetched.append((folder,mail,thread_id))
                except Exception as error:
                    logger.warning('IMAP query skipped for this cycle: %s',type(error).__name__)
                query_cache[query]=fetched
            for folder,mail,thread_id in query_cache[query]:
                mid=message_id(mail)
                if not mid or mid in seen or (mid,case.id) in examined: continue
                examined.add((mid,case.id))
                sender=parseaddr(mail.from_)[1].casefold()
                if sender==config.user_email.casefold(): continue
                headers={k.lower():v for k,v in mail.headers.items()}
                bounce=('mailer-daemon' in sender or sender.startswith('postmaster@') or any('delivery-status' in v.lower() for v in headers.get('content-type',())))
                match=match_candidate(case.id,mail,sent,case.facts_json,domains,sender,config.user_email,thread_id)
                if not match or (bounce and match not in ('thread_id','in_reply_to')): continue
                if company.get('demo') and sender!=config.demo_company_email.casefold() and not bounce:
                    verified,detail=False,'Sender does not match the configured demo address.'
                else: verified,detail=sender_authentication(list(headers.get('authentication-results',())),sender,domains)
                if bounce: verified=False;detail='Delivery status notification needs user confirmation.'
                from .threading_gmail import extract_message_ids
                in_reply_to=next(iter(extract_message_ids(headers.get('in-reply-to',()))),None)
                references=extract_message_ids(headers.get('references',()))
                source=next((m for m in sent if m.message_id==in_reply_to),None)
                data=dict(folder=folder,case_id=case.id,message_id=mid,sender=sender,subject=mail.subject,body=mail.text or '',in_reply_to=in_reply_to,references=references,gmail_thread_id=thread_id,reply_level=source.level.value if source else None,bounced=bounce,match_method=match,sender_verified=verified,verification_detail=detail,needs_confirmation=match=='domain_only' or not verified,uid=str(mail.uid))
                previous=candidates.get(mid);rank=ranks[match]
                if previous is None or rank<previous[0]: candidates[mid]=(rank,[data])
                elif rank==previous[0]: previous[1].append(data)
            if query.startswith(('TO ','CC ','X-GM-THRID ')) and candidates:
                try:
                    address=plus_address(config.user_email,case.id).casefold()
                    owners=sum(plus_address(config.user_email,item[0].id).casefold()==address for item in work)
                except ValueError: owners=0
                if owners==1 and all(len(items)==1 and items[0]['case_id']==case.id and items[0]['match_method'] in ('thread_id','in_reply_to','plus_address') for _,items in candidates.values()):
                    for _,items in candidates.values():
                        data=items[0];found.append(data)
                        if not data['needs_confirmation']: data['label_applied']=label_confirmed(data['folder'],data['uid'])
                    return found
    for _,items in candidates.values():
        ambiguous=len(items)>1
        for data in items:
            if ambiguous: data['needs_confirmation']=True;data['verification_detail']+=' Multiple cases match; user review required.'
            found.append(data)
            if not data['needs_confirmation']: data['label_applied']=label_confirmed(data['folder'],data['uid'])

    return found


def label_confirmed(folder: str,uid: str) -> bool:
    from types import SimpleNamespace
    config=get_settings()
    try:
        with MailBox('imap.gmail.com',timeout=10).login(config.user_email,config.user_email_app_password.get_secret_value()) as box:
            box.folder.set(folder,readonly=False)
            return apply_label(box,SimpleNamespace(uid=uid))
    except Exception as error:
        logger.warning('Label verification skipped: %s',type(error).__name__)
        return False
