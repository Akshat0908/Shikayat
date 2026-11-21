from dataclasses import dataclass
from . import deadlines

@dataclass(frozen=True)
class Decision:
    action: str
    level: str
    reason: str
    requires_approval: bool = True

def decide(level: str, category: str, deflections: int = 0, ack_breached: bool = False, offered: float | None = None, demand: float | None = None, missing_info: bool = False, receipt_confirmed: bool = False) -> Decision:
    if receipt_confirmed: return Decision('resolve',level,'User confirmed money was received.',False)
    if category=='resolution_offered' and offered is not None and demand is not None and offered>=demand:
        return Decision('confirm_receipt',level,'Full demand offered; receipt requires user confirmation.',False)
    if category=='partial_resolution': return Decision('counter',level,'Offer leaves part of the demand unpaid.')
    if category=='info_requested': return Decision('ask_user' if missing_info else 'reply_info',level,'Requested information is missing.' if missing_info else 'Requested information is available in case facts.')
    if category=='rejected' or ack_breached or (category=='deflection' and deflections>=2):
        next_level={'L2':'L3','L3':'L4','L4':'L5','L5':'L5'}[level]
        return Decision('prepare_filing' if next_level in ('L4','L5') else 'escalate',next_level,'Acknowledgment deadline breached.' if ack_breached else 'Rejection or repeated deflection requires the next escalation level.')
    if category=='deflection': return Decision('followup',level,'No concrete commitment; send a firm follow-up.')
    return Decision('wait',level,'No escalation trigger; continue watching the thread.',False)
