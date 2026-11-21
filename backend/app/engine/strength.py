from ..ai.schemas import CaseFacts

def strength(facts: CaseFacts, evidence_count: int) -> tuple[int,str]:
    score=min(20,evidence_count*10)
    score+=15 if facts.amount_inr is not None else 0
    score+=15 if facts.order_id else 0
    score+=10 if facts.purchase_date or any(e.date for e in facts.events) else 0
    score+=min(20,len(facts.contact_attempts)*5)
    score+=10 if facts.days_elapsed is not None and facts.days_elapsed>=14 else 0
    score+=10 if any(a.ticket_id for a in facts.contact_attempts) else 0
    label='Very strong' if score>=90 else 'Strong' if score>=70 else 'Fair' if score>=40 else 'Weak'
    return score,label

async def rationale(facts: CaseFacts, score: int) -> str:
    from ..ai.client import call_structured
    from ..ai.schemas import ShortText
    from ..config import get_settings
    result=await call_structured('strength_rationale',get_settings().model_fast,ShortText,'Write one short sentence explaining the supplied deterministic score. Do not change it or invent facts.',facts.model_dump_json()+f' Score: {score}')
    return result.text
