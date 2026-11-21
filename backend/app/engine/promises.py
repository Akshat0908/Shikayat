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
    for sentence in re.split(r'(?<=[.!?])\s+|\n+',text):
        if not re.search(r'\b(refund|credit|deliver|replace|resolve|process|complete)\w*\b',sentence,re.I): continue
        if not re.search(r'\b(will|within|by|shall|promise|expected|working days|business days)\b',sentence,re.I): continue
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
