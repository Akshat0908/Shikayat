import json
from typing import Any
from ..config import ROOT, Settings, get_settings


def load_companies(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Resolve only the explicitly configured fictional demo mailbox."""
    config = settings or get_settings()
    companies = json.loads((ROOT / "data" / "companies.json").read_text())
    for company in companies:
        if company.get("demo"):
            for role in ("grievance_officer", "nodal_officer"):
                contact = company[role]
                if contact.get("email_env") == "DEMO_COMPANY_EMAIL":
                    contact["email"] = config.demo_company_email.strip() or None
    return companies

async def match_company(name: str | None) -> dict[str, Any] | None:
    from rapidfuzz.fuzz import WRatio
    from ..ai.client import call_structured
    from ..ai.schemas import ShortText
    if not name:
        return None
    candidates=[]
    for company in load_companies():
        score=max(WRatio(name.casefold(),alias.casefold()) for alias in [company['name'],*company['aliases']])
        candidates.append((score,company))
    best=max(score for score,_ in candidates)
    if best<75:
        return None
    tied=[company for score,company in candidates if score==best]
    if len(tied)==1:
        return tied[0]
    answer=await call_structured('company_tie',get_settings().model_fast,ShortText,'Select one exact company id from the candidates, or return empty text if uncertain.',json.dumps({'name':name,'candidates':[c['id'] for c in tied]}))
    return next((c for c in tied if c['id']==answer.text),None)
