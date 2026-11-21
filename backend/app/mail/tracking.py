from urllib.parse import urlencode, quote


def case_tag(case_id: str) -> str:
    return f'[Shikayat #{case_id.replace("-", "")[:8]}]'


def plus_address(email: str, case_id: str) -> str:
    if '@' not in email: raise ValueError('Sender email is not configured')
    local,domain=email.rsplit('@',1)
    if not local or not domain: raise ValueError('Sender email is not configured')
    return f'{local.split("+")[0]}+shk{case_id.replace("-", "")[:8]}@{domain}'


def tracked_subject(subject: str, case_id: str) -> str:
    tag=case_tag(case_id)
    return subject if tag.casefold() in subject.casefold() else f'{subject} {tag}'


def compose_urls(recipient: str, subject: str, body: str, tracking: str) -> dict[str,str]:
    mailto='mailto:'+quote(recipient,safe='@')+'?'+urlencode({'subject':subject,'body':body,'cc':tracking,'reply-to':tracking},quote_via=quote)
    gmail='https://mail.google.com/mail/?'+urlencode({'view':'cm','fs':'1','to':recipient,'su':subject,'body':body,'cc':tracking})
    return {'mailto':mailto,'gmail':gmail}
