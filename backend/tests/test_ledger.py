from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app

def test_ledger_unknown_provenance_is_not_fabricated(tmp_path):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db.sqlite'))
    with TestClient(app,base_url='https://testserver') as client:
        case=client.post('/api/cases/sample/shopkart').json()
        data=client.get(f"/api/cases/{case['id']}/evidence").json()
        amount=next(f for f in data['facts'] if f['field']=='amount_inr')
        assert amount['value']==4299
        assert amount['origin'] is None and amount['verification_state']=='needs_verification'
