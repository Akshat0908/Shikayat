from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


def test_latest_eval_is_explicitly_sample(tmp_path):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/eval.db'))
    with TestClient(app,base_url='https://testserver') as client:
        result=client.get('/api/eval/latest').json()
    assert result['data_source']=='sample'
    assert result['evaluated_at'] is None and result['model']=='Not run'
    assert result['case_count']==len(result['cases'])==20
    for case in result['cases']:
        assert len(case['baseline']['metrics'])==len(case['shikayat']['metrics'])==6
        assert 'Illustrative' in case['baseline']['output'] and 'Illustrative' in case['shikayat']['output']


def test_static_proof_route(tmp_path):
    exported=tmp_path/'out'
    (exported/'proof').mkdir(parents=True)
    (exported/'proof'/'index.html').write_text('proof page')
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/static.db',frontend_dist=exported))
    with TestClient(app,base_url='https://testserver') as client:
        assert client.get('/proof/').text=='proof page'
        assert client.get('/api/eval/latest').json()['data_source']=='sample'
