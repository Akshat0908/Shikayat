"""Official-contact discovery. Search results are leads until the user confirms them."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..ai.client import call_structured
from ..config import ROOT, get_settings
from ..engine.company import load_companies

router=APIRouter(prefix='/api/companies')
Role=Literal['grievance_officer','nodal_officer']
DISALLOWED_DOMAINS={'amazon.in','flipkart.com','facebook.com','instagram.com','youtube.com','linkedin.com','x.com','twitter.com','reddit.com','google.com','justdial.com','trustpilot.com','voxya.com'}

class Lead(BaseModel):
    email: str | None
    officer_name: str | None
    role: Role
    source_url: str | None
    evidence_quote: str | None
    contact_type: Literal['grievance_officer','customer_support'] = 'grievance_officer'

class DomainSuggestion(BaseModel):
    domain: str | None

class DiscoveryRequest(BaseModel):
    role: Role = 'grievance_officer'
    confirmed_domain: str | None = None
    edited_domain: bool = False

class Confirmation(BaseModel):
    role: Role = 'grievance_officer'


def get_company(company_id: str) -> dict:
    company=next((item for item in load_companies() if item['id']==company_id),None)
    if not company: raise HTTPException(404,'Company not found')
    if company.get('demo'): raise HTTPException(422,'Discovery is unavailable for the fictional company')
    return company


def domain_name(value: str | None) -> str | None:
    value=(value or '').lower().strip().rstrip('.')
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',value): return None
    return value


def validate(lead: Lead, domains: list[str], role: Role) -> list[str]:
    errors=[]
    official=[domain_name(item) for item in domains];official=[d for d in official if d]
    try:
        parsed=urlsplit(lead.source_url or '')
        host=(parsed.hostname or '').lower().rstrip('.')
        safe=parsed.scheme=='https' and not parsed.username and not parsed.password and parsed.port in (None,443)
    except ValueError: host='';safe=False
    if not safe or not any(host==d or host.endswith('.'+d) for d in official): errors.append('Source URL is not on the official domain')
    address=lead.email or ''
    if not re.fullmatch(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+',address): errors.append('Email address is missing or invalid')
    if address and address not in (lead.evidence_quote or ''): errors.append('Email does not appear literally in the evidence quote')
    if not address or not any(address.rsplit('@',1)[-1].casefold()==d for d in official): errors.append('Email domain does not match an official domain')
    if lead.role!=role: errors.append('Contact role does not match requested role')
    return errors


def cache_path(company_id: str, role: str) -> Path:
    path=ROOT/'var'/'company_discovery';path.mkdir(parents=True,exist_ok=True)
    return path/f'{company_id}-{role}.json'


def read_cache(path: Path) -> dict | None:
    try:
        data=json.loads(path.read_text()); timestamp=datetime.fromisoformat(data['at'])
        return data if datetime.now(timezone.utc)-timestamp < timedelta(days=7) else None
    except (OSError,ValueError,KeyError,TypeError): return None


def save(path: Path, value: dict) -> None:
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value));temp.replace(path)


def update_company(company_id: str, update) -> None:
    path=ROOT/'var'/'provisional_companies.json' if company_id.startswith('provisional-') else ROOT/'data'/'companies.json'
    data=json.loads(path.read_text())
    company=next(item for item in data if item['id']==company_id);update(company)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n');temp.replace(path)


@router.post('/{company_id}/discover')
async def discover(company_id: str, request: DiscoveryRequest) -> dict:
    company=get_company(company_id);role=request.role; path=cache_path(company_id,role)
    cached=read_cache(path);domains=company.get('verified_domains',[])
    if not domains:
        if request.confirmed_domain:
            proposed=(cached or {}).get('suggested_domain')
            domain=domain_name(request.confirmed_domain)
            if not domain or domain in DISALLOWED_DOMAINS or (domain!=proposed and not (request.edited_domain and proposed)): raise HTTPException(422,'Confirm the suggested official domain first')
            update_company(company_id,lambda item:item.update(verified_domains=[domain]));domains=[domain];cached=None
        else:
            if not cached or not cached.get('suggested_domain'):
                suggestion=await call_structured('company_domain',get_settings().model_fast,DomainSuggestion,'Search for the official website of this company. Exclude marketplaces, review sites, social media and complaint aggregators. Return its bare domain, or null if unsure. User confirmation is required.',company['name'],search_domains=[])
                proposed=domain_name(suggestion.domain)
                if not proposed or proposed in DISALLOWED_DOMAINS: return {'status':'domain_unknown','message':'Could not identify an official domain'}
                cached={'at':datetime.now(timezone.utc).isoformat(),'suggested_domain':proposed};save(path,cached)
            return {'status':'confirm_domain','domain':cached['suggested_domain']}
    if cached and cached.get('lead') and cached.get('domains')==domains and cached.get('version')==2:
        lead=Lead.model_validate(cached['lead']);errors=validate(lead,domains,role)
        return {'status':'unverified_lead' if errors else 'awaiting_confirmation','lead':lead.model_dump(),'errors':errors,'cached':True}
    try:
        lead=await call_structured('contact_discovery',get_settings().model_smart,Lead,'Find the requested official grievance contact. If no designated grievance officer contact exists, find an officially published customer support email and set contact_type to customer_support; otherwise set grievance_officer. Use only official-domain pages. Return only exact text from the source; never invent details. If unavailable return null fields.',f"Company: {company['name']}; role: {role}. Find the official grievance redressal page and its published contact. If available prioritize this company-recorded source: {company.get(role,{}).get('source_url') or 'none'}.",search_domains=domains)
    except Exception as error:
        raise HTTPException(503,'Official contact search failed; please verify manually') from error
    errors=validate(lead,domains,role)
    save(path,{'at':datetime.now(timezone.utc).isoformat(),'lead':lead.model_dump(),'domains':domains,'version':2})
    return {'status':'unverified_lead' if errors else 'awaiting_confirmation','lead':lead.model_dump(),'errors':errors,'cached':False}


@router.post('/{company_id}/confirm-contact')
async def confirm_contact(company_id: str, request: Confirmation) -> dict:
    company=get_company(company_id);cached=read_cache(cache_path(company_id,request.role))
    if not cached or not cached.get('lead'): raise HTTPException(409,'Find the contact before confirming')
    lead=Lead.model_validate(cached['lead']);errors=validate(lead,company.get('verified_domains',[]),request.role)
    if errors: raise HTTPException(422,'Unverified lead cannot be confirmed: '+ '; '.join(errors))
    def apply(item):
        item[request.role].update(email=lead.email,name=lead.officer_name,source_url=lead.source_url,verified=True,last_checked=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),contact_type=lead.contact_type)
    update_company(company_id,apply)
    return {'status':'confirmed','contact':lead.model_dump()}
