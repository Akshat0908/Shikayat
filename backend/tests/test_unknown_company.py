import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import Session
from backend.app.api import company_cases
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case, Evidence


def test_existing_cases_link_and_domain_agreement_runs_search(tmp_path,monkeypatch):
    company={'id':'provisional-leaf','name':'Leaf Studios','verified_domains':[],'grievance_officer':{},'nodal_officer':{}}
    monkeypatch.setattr(company_cases,'provisional_company',lambda name:company)
    monkeypatch.setattr(company_cases,'load_companies',lambda:[company])
    async def inspect(*args,**kwargs): return company_cases.ScreenshotDomains(domains=['leafstudios.in'])
    monkeypatch.setattr(company_cases,'call_structured',inspect)
    calls=[]
    async def discover(id, request):
        calls.append(request.confirmed_domain)
        return {'status':'awaiting_confirmation','lead':{'email':'help@leafstudios.in'}} if request.confirmed_domain else {'status':'confirm_domain','domain':'leafstudios.in'}
    monkeypatch.setattr(company_cases,'discover',discover)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',user_email='',demo_company_email=''))
    with TestClient(app) as client:
        image=tmp_path/'evidence';image.write_bytes(b'\x89PNGfake')
        with Session(app.state.engine) as s:
            a=Case(title='a',facts_json={'company_name':'Leaf Studios'});b=Case(title='b',facts_json={'company_name':'Leaf Studios'});s.add_all([a,b]);s.commit();s.refresh(a);s.refresh(b); aid=a.id;bid=b.id;s.add(Evidence(case_id=aid,kind='screenshot',path=str(image)));s.commit()
        response=client.post(f'/api/cases/{aid}/discover-contact').json()
        assert response['domain_auto_confirmed'] and response['status']=='awaiting_confirmation'
        assert calls==[None,'leafstudios.in']
        with Session(app.state.engine) as s: assert s.get(Case,bid).company_id=='provisional-leaf'


def test_disagreement_requires_user_confirmation(tmp_path,monkeypatch):
    company={'id':'provisional-leaf','name':'Leaf Studios','verified_domains':[],'grievance_officer':{},'nodal_officer':{}}
    monkeypatch.setattr(company_cases,'load_companies',lambda:[company]);calls=[]
    async def discover(id, request): calls.append(request.confirmed_domain);return {'status':'confirm_domain','domain':'other.test'}
    monkeypatch.setattr(company_cases,'discover',discover)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',user_email='',demo_company_email=''))
    with TestClient(app) as client:
        with Session(app.state.engine) as s:
            case=Case(title='a',company_id=company['id'],facts_json={'screenshot_domains':['leafstudios.in']});s.add(case);s.commit();s.refresh(case);case_id=case.id
        assert client.post(f'/api/cases/{case_id}/discover-contact').json()['status']=='confirm_domain'
        assert calls==[None]


def test_nch_pack_is_a_draft_and_labels_sample(tmp_path):
    from sqlmodel import select
    from backend.app.models import Event
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',user_email='',demo_company_email=''))
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            case=Case(title='Broken item',facts_json={'looks_like_sample':True,'company_name':'Leaf'});session.add(case);session.commit();session.refresh(case);case_id=case.id
        assert client.post(f'/api/cases/{case_id}/nch-pack').json()['status']=='draft_ready'
        with Session(app.state.engine) as session:
            event=session.exec(select(Event).where(Event.type=='nch_pack')).one()
            assert 'SAMPLE DATA' in event.payload_json['body'] and 'file themselves' in event.reason
