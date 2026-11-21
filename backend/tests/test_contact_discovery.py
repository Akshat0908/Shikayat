import json
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from backend.app.api import companies
from backend.app.main import create_app
from backend.app.config import Settings


def test_validation_rejects_bad_source_quote_email_and_role():
    make=lambda **values:companies.Lead(**({'email':'officer@flipkart.com','officer_name':None,'role':'grievance_officer','source_url':'https://www.flipkart.com/contact','evidence_quote':'Email: officer@flipkart.com'}|values))
    assert not companies.validate(make(),['flipkart.com'],'grievance_officer')
    for lead in (make(source_url='https://flipkart.com.attacker.test/x'),make(source_url='https://user@flipkart.com/x'),make(email='officer@attacker.test',evidence_quote='officer@attacker.test'),make(evidence_quote='No address'),make(role='nodal_officer')):
        assert companies.validate(lead,['flipkart.com'],'grievance_officer')


def test_discovery_requires_confirmation_and_caches(tmp_path,monkeypatch):
    root=tmp_path; (root/'data').mkdir(); path=root/'data'/'companies.json'
    original={'id':'company','name':'Company','demo':False,'verified_domains':['company.test'],'grievance_officer':{'verified':False,'email':None},'nodal_officer':{'verified':False,'email':None}}
    path.write_text(json.dumps([original]));monkeypatch.setattr(companies,'ROOT',root)
    monkeypatch.setattr(companies,'load_companies',lambda:json.loads(path.read_text()))
    calls=[]
    async def search(*args,**kwargs):
        calls.append(kwargs['search_domains']);return companies.Lead(email='grievance@company.test',officer_name=None,role='grievance_officer',source_url='https://www.company.test/grievance',evidence_quote='Email: grievance@company.test')
    monkeypatch.setattr(companies,'call_structured',search)
    app=create_app(Settings(database_url=f'sqlite:///{root}/test.db',user_email='',demo_company_email=''))
    with TestClient(app) as client:
        response=client.post('/api/companies/company/discover',json={});assert response.json()['status']=='awaiting_confirmation'
        assert not json.loads(path.read_text())[0]['grievance_officer']['verified']
        assert client.post('/api/companies/company/discover',json={}).json()['cached'] is True
        assert calls==[['company.test']]
        assert client.post('/api/companies/company/confirm-contact',json={}).status_code==200
        assert json.loads(path.read_text())[0]['grievance_officer']['verified'] is True
        # Confirmation does not bypass the public-demo SMTP guard.
        import asyncio
        import pytest
        from backend.app.mail import smtp_send
        monkeypatch.setattr(smtp_send,'get_settings',lambda:Settings(public_demo=True,send_enabled=True,autopilot_allowlist='demo@example.test'))
        with pytest.raises(ValueError,match='Sending disabled on the public demo'):
            asyncio.run(smtp_send.send_email(json.loads(path.read_text())[0]['grievance_officer'],'Subject','Body',True,False,case_id='case'))
        # An expired lead cannot be confirmed.
        cache=companies.cache_path('company','grievance_officer');data=json.loads(cache.read_text());data['at']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat();cache.write_text(json.dumps(data))
        assert client.post('/api/companies/company/confirm-contact',json={}).status_code==409


def test_domain_suggestion_needs_confirmation(tmp_path,monkeypatch):
    (tmp_path/'data').mkdir();path=tmp_path/'data'/'companies.json';path.write_text(json.dumps([{'id':'c','name':'Company','demo':False,'verified_domains':[],'grievance_officer':{},'nodal_officer':{}}]))
    monkeypatch.setattr(companies,'ROOT',tmp_path);monkeypatch.setattr(companies,'load_companies',lambda:json.loads(path.read_text()))
    async def fake(*args,**kwargs):
        if kwargs.get('search_domains'): return companies.Lead(email=None,officer_name=None,role='grievance_officer',source_url=None,evidence_quote=None)
        return companies.DomainSuggestion(domain='company.test')
    monkeypatch.setattr(companies,'call_structured',fake)
    with TestClient(create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',user_email='',demo_company_email=''))) as client:
        assert client.post('/api/companies/c/discover',json={}).json()['status']=='confirm_domain'
        assert json.loads(path.read_text())[0]['verified_domains']==[]
        assert client.post('/api/companies/c/discover',json={'confirmed_domain':'evil.test'}).status_code==422
        assert client.post('/api/companies/c/discover',json={'confirmed_domain':'company.test'}).json()['status']=='unverified_lead'
        assert client.post('/api/companies/c/confirm-contact',json={}).status_code==422
