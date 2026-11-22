import pytest
from backend.app.engine.receipt import user_confirmed_receipt

@pytest.mark.parametrize('text,amount,expected',[
 ('I received the refund of ₹2,300 in my bank account.',2300,True),
 ('The refund of ₹2,300 reached my bank account.',2300,True),
 ('I got the refund yesterday. ₹2,300 actually reached my account.',2300,True),
 ('I have not received the refund of ₹2,300.',2300,False),
 ('The company said "I received the refund of ₹2,300."',2300,False),
 ('I got a refund of ₹300.',2300,False),
 ('From: merchant@example.test\nI received the refund of ₹2,300.',2300,False),
 ('The company says the refund of ₹2,300 was credited.',2300,False),
 ('I received the refund.',2300,False),
])
def test_user_receipt_requires_explicit_full_amount(text,amount,expected):
    assert user_confirmed_receipt(text,amount) is expected


def test_explicit_typed_receipt_closes_new_case(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.config import Settings,ROOT
    from backend.app.ai.schemas import CaseFacts
    import backend.app.api.cases as route
    facts=CaseFacts.model_validate_json((ROOT/'data/samples/shopkart/facts.json').read_text())
    async def extracted(*args): return facts
    async def matched(*args): return None
    async def explain(*args): return 'Evidence reviewed.'
    monkeypatch.setattr(route,'extract_case',extracted)
    monkeypatch.setattr(route,'match_company',matched)
    monkeypatch.setattr(route,'provisional_company',lambda name:{'id':'example'})
    monkeypatch.setattr(route,'rationale',explain)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/test.db'))
    with TestClient(app,base_url='https://testserver') as client:
        response=client.post('/api/cases',data={'text':'I received the refund of ₹4,299 in my account.'})
        assert response.status_code==200,response.text
        case=response.json();assert case['status']=='RESOLVED' and case['recovered_inr']==4299
        board=client.get('/api/cases/'+case['id']+'/board').json()
        assert any(event['type']=='resolved' and event['actor']=='user' for event in board['events'])
