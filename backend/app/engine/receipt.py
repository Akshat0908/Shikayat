"""Recognize explicit first-person receipt in the user's own typed input."""
import re


def user_confirmed_receipt(text: str, amount: float | None) -> bool:
    if amount is None or re.search(r'(?im)^\s*(?:from|subject|forwarded message):',text):
        return False
    explicit_refund=bool(re.search(r'\bi\s+(?:have\s+|actually\s+)?(?:received|got)\b[^.!?\n]{0,80}\brefund\b',text,re.I))
    for sentence in re.split(r'(?<=[.!?])\s+|\n+',text):
        lower=sentence.casefold()
        if any(mark in sentence for mark in ('"','“','”','>')) or re.search(r'\b(?:not|never|no|didn.t|hasn.t|haven.t|waiting|promised|says|said|wrote|claims?)\b',lower):
            continue
        if not re.search(r'\brefund\b',lower) and not explicit_refund: continue
        first_person=re.search(r'\bi\s+(?:have\s+|actually\s+)?(?:received|got)\b',lower)
        credited=re.search(r'\b(?:reached|credited to|arrived in)\s+my\s+(?:bank\s+)?account\b',lower)
        if not (first_person or credited): continue
        amounts=[float(x.replace(',','')) for x in re.findall(r'(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d{1,2})?)',lower)]
        if any(value>=amount for value in amounts): return True
    return False
