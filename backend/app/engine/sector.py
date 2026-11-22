"""Conservative applicability: regulated sectors and offline purchases take precedence."""
import re

REGULATED={'banking','insurance','telecom','airlines','airline'}


def sector_from_text(text: str) -> str | None:
    text=text.casefold()
    patterns={
        'insurance':r'\b(?:insurance|insurer|policyholder|insurance claim|claims? adjuster)\b',
        'banking':r'\b(?:banking|bank fee|bank charge|credit card dispute|bank loan|bank service)\b',
        'telecom':r'\b(?:telecom|telecommunication|mobile network|mobile plan|broadband|mobile recharge)\b',
        'airlines':r'\b(?:airline|airlines|flight|airfare|air carrier)\b',
    }
    return next((name for name,pattern in patterns.items() if re.search(pattern,text)),None)


def effective_sector(company: dict | None, facts: dict) -> str | None:
    company_sector=str((company or {}).get('sector') or '').casefold()
    if (company or {}).get('id') in ('indigo','air_india'): company_sector='airlines'
    reported=str(facts.get('sector') or '').casefold()
    signals=' '.join([company_sector,*(str(facts.get(key) or '') for key in ('sector','company_name','issue_summary_en'))])
    regulated=company_sector if company_sector in REGULATED else sector_from_text(signals)
    if regulated: return regulated
    if reported in REGULATED: return reported
    if facts.get('purchase_channel')=='offline': return 'offline'
    if company_sector=='e-commerce' or reported=='e-commerce' or facts.get('purchase_channel') in ('brand_website','brand_app','marketplace') or facts.get('online_purchase') is True:
        return 'e-commerce'
    return company_sector or reported or None


def sector_message(company: dict | None, facts: dict) -> str | None:
    sector=effective_sector(company,facts)
    if sector=='e-commerce': return None
    return 'Sector-specific rules not configured' if sector in REGULATED or sector=='offline' else 'Online purchase channel needs verification'
