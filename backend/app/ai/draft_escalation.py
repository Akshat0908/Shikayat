import json
from .client import call_structured
from .draft_complaint import EmailDraft,verified_refs,validate_draft
from ..config import get_settings

async def draft_escalation(facts: dict, thread: list[dict], reason: str, deadline: str) -> EmailDraft:
    result=await call_structured('draft_escalation',get_settings().model_smart,EmailDraft,'Draft a firm polite escalation under 220 words. Use only supplied facts and verified legal refs. Quote prior thread dates accurately. No invented names, addresses, legal references or URLs. Use exact deadline_date. No threats.',json.dumps(dict(facts=facts,thread=thread,reason=reason,deadline_date=deadline,verified_refs=verified_refs())))
    return validate_draft(result,deadline)
