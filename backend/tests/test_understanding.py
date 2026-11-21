import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.ai.schemas import CaseFacts
from backend.app.engine.strength import strength
from backend.app.engine.company import match_company
from backend.app.main import create_app
from backend.app.config import Settings, ROOT

def test_company_matching() -> None:
    assert asyncio.run(match_company('shop kart'))['id']=='shopkart'
    assert asyncio.run(match_company('Amazon India'))['id']=='amazon_india'
    assert asyncio.run(match_company('unrelated unknown business')) is None
    assert asyncio.run(match_company(None)) is None

def test_strength() -> None:
    facts=CaseFacts.model_validate_json((ROOT/'data/samples/shopkart/facts.json').read_text())
    assert strength(facts,1)==(75,'Strong')
    facts.amount_inr=None;facts.order_id=None;facts.purchase_date=None;facts.events=[];facts.contact_attempts=[];facts.days_elapsed=None
    assert strength(facts,0)==(0,'Weak')

def test_sample(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(database_url=f'sqlite:///{tmp_path}/test.db'))) as client:
        response=client.post('/api/cases/sample/shopkart')
        assert response.status_code==200,response.text
        result=response.json()
        assert result['amount_inr']==4299
        assert result['company_id']=='shopkart'
        assert result['strength_label']=='Strong'
