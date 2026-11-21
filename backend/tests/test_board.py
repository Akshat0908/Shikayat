from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app

def test_case_listing_and_board(tmp_path):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/board.db',demo_mode=False))
    with TestClient(app) as client:
        case=client.post('/api/cases/sample/shopkart').json()
        assert any(c['id']==case['id'] for c in client.get('/api/cases').json())
        board=client.get('/api/cases/'+case['id']+'/board').json()
        assert board['case']['id']==case['id'] and board['events']
        assert client.get('/api/demo/settings').json()=={'demo_mode':False}
