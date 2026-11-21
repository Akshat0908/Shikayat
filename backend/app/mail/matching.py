"""Conservative candidate matching and Gmail authentication-result validation."""
import re
from email.utils import parseaddr
from .tracking import case_tag,plus_address


def verified_domains(company: dict, demo_address: str) -> list[str]:
    if company.get('demo'):
        return [demo_address.rsplit('@',1)[1].casefold()] if '@' in demo_address else []
    return [d.casefold().strip('.') for d in company.get('verified_domains',[]) if re.fullmatch(r'[A-Za-z0-9.-]+',d)]


def sender_authentication(headers: list[str], sender: str, domains: list[str]) -> tuple[bool,str]:
    address=parseaddr(sender)[1].casefold()
    if '@' not in address or address.rsplit('@',1)[1] not in domains: return False,'Sender domain is not verified for this company.'
    # Gmail adds its authentication result at the trust boundary. Never trust a
    # later, potentially attacker-supplied Authentication-Results header.
    for header in headers[:1]:
        if not re.match(r'^\s*mx\.google\.com\s*;',header,re.I): continue
        for match in re.finditer(r'(?:^|;)\s*(dkim|spf)\s*=\s*pass\b([^;]*)',header,re.I):
            method=match.group(1).lower(); details=match.group(2)
            field=re.search(r'\bheader\.(?:d|i)\s*=\s*([^\s;]+)',details,re.I) if method=='dkim' else re.search(r'\bsmtp\.mailfrom\s*=\s*([^\s;]+)',details,re.I)
            if not field: continue
            domain=field.group(1).strip('<>').rsplit('@',1)[-1].strip('.').casefold()
            if domain in domains: return True,method.upper()+' pass · company domain'
    return False,'No trusted SPF or DKIM pass for the verified company domain.'


def match_candidate(case_id: str, mail, sent: list, facts: dict, domains: list[str], sender: str, user_email: str, thread_id: str | None = None) -> str | None:
    headers={k.lower():v for k,v in mail.headers.items()}
    if thread_id and any(getattr(m,'gmail_thread_id',None)==thread_id for m in sent): return 'thread_id'
    refs=''.join(''.join([*headers.get('references',()),*headers.get('in-reply-to',())]).split())
    if any(m.message_id and ''.join(m.message_id.split()) in refs for m in sent): return 'in_reply_to'
    addresses=' '.join([*headers.get('to',()),*headers.get('cc',())]).casefold()
    try:
        if plus_address(user_email,case_id).casefold() in addresses: return 'plus_address'
    except ValueError: pass
    if case_tag(case_id).casefold() in (mail.subject or '').casefold(): return 'case_tag'
    text=(mail.subject or '')+' '+(mail.text or '')
    tickets=facts.get('known_ticket_ids',[])
    if any(t and str(t).casefold() in text.casefold() for t in tickets): return 'ticket_id'
    domain=sender.rsplit('@',1)[-1].casefold() if '@' in sender else ''
    order=facts.get('order_id')
    if domain in domains and order and str(order).casefold() in text.casefold(): return 'order_id'
    if domain in domains: return 'domain_only'
    return None
