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
    with TestClient(app,base_url='https://testserver') as client:
        response=client.post('/api/companies/company/discover',json={});assert response.json()['status']=='awaiting_confirmation'
        assert not json.loads(path.read_text())[0]['grievance_officer']['verified']
        assert client.post('/api/companies/company/discover',json={}).json()['cached'] is True
        assert calls==[['company.test']]
        assert client.post('/api/companies/company/confirm-contact',json={}).status_code==200
        assert json.loads(path.read_text())[0]['grievance_officer']['verified'] is True
        # A confirmed contact still cannot be sent directly by an unsigned visitor.
        assert client.post('/api/cases/unknown/approve').status_code==404
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


def test_privacy_grievance_is_not_a_consumer_contact():
    lead=companies.Lead(email='developer@company.test',officer_name=None,role='grievance_officer',source_url='https://company.test/privacy-policy',evidence_quote='For processing of information email developer@company.test')
    assert 'Privacy-only contact is not established for consumer complaints' in companies.validate(lead,['company.test'],'grievance_officer')
    support=companies.Lead(email='support@company.test',officer_name=None,role='grievance_officer',source_url='https://company.test/contact',evidence_quote='E-MAIL: support@company.test',contact_type='customer_support')
    assert not companies.validate(support,['company.test'],'grievance_officer')


def test_privacy_lead_falls_back_to_customer_support(tmp_path,monkeypatch):
    (tmp_path/'data').mkdir();path=tmp_path/'data'/'companies.json'
    path.write_text(json.dumps([{'id':'c','name':'Company','demo':False,'verified_domains':['company.test'],'grievance_officer':{},'nodal_officer':{}}]))
    monkeypatch.setattr(companies,'ROOT',tmp_path);monkeypatch.setattr(companies,'load_companies',lambda:json.loads(path.read_text()))
    calls=[]
    async def search(*args,**kwargs):
        calls.append(True)
        if len(calls)==1:return companies.Lead(email='developer@company.test',officer_name=None,role='grievance_officer',source_url='https://company.test/privacy-policy',evidence_quote='processing of information developer@company.test')
        return companies.Lead(email='support@company.test',officer_name=None,role='grievance_officer',source_url='https://company.test/contact',evidence_quote='Email: support@company.test',contact_type='customer_support')
    monkeypatch.setattr(companies,'call_structured',search)
    with TestClient(create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',user_email='',demo_company_email=''))) as client:
        result=client.post('/api/companies/c/discover',json={}).json()
        assert len(calls)==2 and result['status']=='awaiting_confirmation'
        assert result['lead']['email']=='support@company.test' and result['lead']['contact_type']=='customer_support'
        assert not json.loads(path.read_text())[0]['grievance_officer'].get('verified')
