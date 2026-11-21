"""Determine whether the configured e-commerce rules apply to this case."""

REGULATED={'banking','insurance','telecom','airlines','airline'}


def effective_sector(company: dict | None, facts: dict) -> str | None:
    sector=(company or {}).get('sector')
    if sector in REGULATED: return sector
    if sector=='e-commerce' or facts.get('purchase_channel') in ('brand_website','brand_app','marketplace') or facts.get('online_purchase') is True:
        return 'e-commerce'
    return sector


def sector_message(company: dict | None, facts: dict) -> str | None:
    sector=effective_sector(company,facts)
    if sector=='e-commerce': return None
    return 'Sector-specific rules not configured' if sector in REGULATED else 'Online purchase channel needs verification'
