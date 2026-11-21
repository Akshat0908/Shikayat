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
