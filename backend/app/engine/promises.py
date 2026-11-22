"""Deterministic interpretation of dated company commitments."""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

@dataclass(frozen=True)
class Promise:
    promised_date: date
    grace_until: datetime
    quote: str
    exceeds_redress: bool


def promise_from_reply(text: str, extracted_date: str | None, received_at: datetime, redress_due: datetime | None) -> Promise | None:
    # Only accept a date tied to a sentence containing a concrete commitment.
    # Ignore quoted earlier correspondence; it is not a new company commitment.
    text = unquoted_reply(text)
    for sentence in re.split(r'(?<=[.!?])\s+|\n+',text):
        if not re.search(r'\b(refund|credit|deliver|replace|resolve|process|complete)\w*\b',sentence,re.I): continue
        if not re.search(r'\b(will|shall|promise|committed|expected)\b',sentence,re.I): continue
        match=re.search(r'\b(\d+)\s*(?:[-–]\s*(\d+)\s*)?(working|business|calendar)?\s*days?\b',sentence,re.I)
        target=None
        if match:
            days=int(match.group(2) or match.group(1))
            if days>365: continue
            target=received_at.date()
            for _ in range(days):
                target+=timedelta(days=1)
                if match.group(3) and match.group(3).lower() in ('working','business'):
                    while target.weekday()>=5: target+=timedelta(days=1)
        elif extracted_date:
            try:
                candidate=date.fromisoformat(extracted_date)
                # Require the supplied year/month/day or a recognizable written date in the sentence.
                forms=(candidate.isoformat(),candidate.strftime('%d/%m/%Y'),candidate.strftime('%d-%m-%Y'),candidate.strftime('%d %B %Y'),candidate.strftime('%d %b %Y'))
                yearless=(f'{candidate.day} {candidate:%B}',f'{candidate.day} {candidate:%b}',f'{candidate:%B} {candidate.day}',f'{candidate:%b} {candidate.day}')
                if any(form.casefold() in sentence.casefold() for form in forms) or (candidate.year==received_at.year and any(re.search(r'(?<!\d)'+re.escape(form)+r'(?!\d)',sentence,re.I) for form in yearless)): target=candidate
            except ValueError: pass
        if target and target>=received_at.date():
            grace=datetime.combine(target+timedelta(days=1),time.max,tzinfo=timezone.utc)
            return Promise(target,grace,sentence.strip(),bool(redress_due and target>redress_due.date()))
    return None


def unquoted_reply(text: str) -> str:
    # Gmail may wrap the "On ... wrote:" separator across multiple lines.
    separator = re.search(r'(?im)^\s*On [^\n]*(?:\n(?!\s*>)[^\n]*){0,3}?\bwrote:\s*$', text)
    if separator:
        text = text[:separator.start()]
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith('>'))


def promise_is_real(promise: dict, messages: list) -> bool:
    quote = str(promise.get('quote') or '')
    if not quote or quote.lstrip().startswith('>'):
        return False
    for message in messages:
        if message.direction != 'in' or not message.classification_json.get('promised_action'):
            continue
        if quote in unquoted_reply(message.body_text):
            parsed = promise_from_reply(quote, promise.get('promised_date'), message.sent_at, None)
            if parsed and parsed.promised_date.isoformat() == promise.get('promised_date'):
                return True
    return False


def promise_status_text(promise: dict | None, messages: list, remedy: str | None, checkback_date: str | None = None) -> str | None:
    if not promise:
        return None
    if promise_is_real(promise, messages):
        return f"Waiting on their promise: {remedy or 'your requested remedy'} by {promise['promised_date']}"
    if checkback_date:
        return f"No date given by the company. Shikayat will follow up on {checkback_date} if nothing changes."
    return 'No date given by the company. No follow-up is scheduled.'
