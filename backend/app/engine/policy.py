from dataclasses import dataclass
from . import deadlines

@dataclass(frozen=True)
class Decision:
    action: str
    level: str
    reason: str
    requires_approval: bool = True

def decide(level: str, category: str, deflections: int = 0, ack_breached: bool = False, offered: float | None = None, demand: float | None = None, missing_info: bool = False, receipt_confirmed: bool = False, sector: str | None = 'e-commerce', followups: int = 0, followup_limit: int = 3, redress_breached: bool = False, paused: bool = False, bounced: bool = False, outbound_count: int = 0, outbound_limit: int = 8, needs_refund_proof: bool = False, chargeback_pending: bool = False) -> Decision:
    if receipt_confirmed: return Decision('resolve',level,'User confirmed money was received.',False)
    if paused: return Decision('wait',level,'Case paused by the user.',False)
    if level in ('L4','L5'): return Decision('wait',level,'Company route exhausted; no further emails will be sent.',False)
    if bounced: return Decision('prepare_filing','L4','Delivery failed; stop emailing and prepare an NCH-ready complaint.',True)
    if sector != 'e-commerce': return Decision('user_review',level,'Sector-specific rules not configured; user review is required.')
    if chargeback_pending: return Decision('user_review',level,'A chargeback is active; preserve evidence and check the bank’s response deadlines before further action.')
    if needs_refund_proof: return Decision('reply_info',level,'Refund initiation is unverified; request the transaction reference, date, amount and payment method.')
    if category=='resolution_offered' and offered is not None and demand is not None and offered>=demand:
        return Decision('confirm_receipt',level,'Full demand offered; receipt requires user confirmation.',False)
    if category=='partial_resolution': return Decision('offer_choice',level,'Offer is partial or a voucher; user must choose whether to accept or counter.')
    if outbound_count>=outbound_limit: return Decision('prepare_filing','L4','The case reached the outbound email limit; prepare an NCH-ready complaint.',True)
    if category=='info_requested': return Decision('ask_user' if missing_info else 'reply_info',level,'Requested information is missing.' if missing_info else 'Requested information is available in case facts.')
    if category=='rejected' or redress_breached or (ack_breached and followups>0) or (category=='deflection' and deflections>=2) or (category=='deflection' and followups>=followup_limit):
        next_level={'L2':'L3','L3':'L4','L4':'L5','L5':'L5'}[level]
        return Decision('prepare_filing' if next_level in ('L4','L5') else 'escalate',next_level,'One-month redressal period expired.' if redress_breached else 'No acknowledgment after a follow-up.' if ack_breached else 'Rejection, repeated deflection, or follow-up limit requires the next escalation level.')
    if ack_breached: return Decision('followup',level,'No acknowledgment within 48 hours; send a follow-up.')
    if category=='deflection': return Decision('followup',level,'No concrete commitment; send a firm follow-up.')
    return Decision('wait',level,'No escalation trigger; continue watching the thread.',False)
