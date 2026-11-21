"""Record permanent SMTP recipient failures without storing sensitive server text."""
import smtplib
from sqlmodel import Session
from ..models import Case, CaseStatus, Evidence, Event, Level


def permanently_blocked(error: Exception) -> bool:
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return bool(error.recipients) and all(500 <= int(value[0]) < 600 for value in error.recipients.values())
    return isinstance(error,smtplib.SMTPDataError) and 500 <= error.smtp_code < 600


def record_blocked(engine, case_id: str) -> None:
    with Session(engine) as session:
        case=session.get(Case,case_id)
        if not case: return
        reason='The mail server permanently rejected delivery; stop emailing and prepare an NCH-ready complaint.'
        case.facts_json={**case.facts_json,'recipient_bounced':True};case.level=Level.L4;case.status=CaseStatus.NEEDS_INFO
        body=f"Issue: {case.facts_json.get('issue_summary_en') or case.title}\nRequested remedy: {case.demand or 'Needs user review'}\nPlease review the case evidence and correspondence."
        session.add(case)
        session.add(Evidence(case_id=case_id,kind='email',transcript='SMTP recipient delivery was permanently rejected.',extracted_json={'origin':'smtp-blocked'}))
        session.add(Event(case_id=case_id,actor='system',type='bounce',title='Recipient blocked',reason=reason))
        # Portal URL is published by the Department of Consumer Affairs:
        # https://consumeraffairs.gov.in/pages/public-grivance
        session.add(Event(case_id=case_id,actor='system',type='nch_pack',title='NCH-ready complaint',reason=reason,payload_json={'body':body,'portal_url':'https://consumerhelpline.gov.in/public/'}))
        session.commit()
