from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


def test_only_public_experiment_configuration_is_exposed(tmp_path):
    config=Settings(database_url=f'sqlite:///{tmp_path}/experiment.db',flagsmith_environment_id='public-env-key',flagsmith_api_url='https://flags.example.test/api/v1/',flagsmith_events_url='https://events.example.test/',admin_passcode='private-test-value',openai_api_key='private-api-value',user_email_app_password='private-mail-value')
    with TestClient(create_app(config),base_url='https://testserver') as client:
        response=client.get('/api/experiment/config')
        assert response.status_code==200
        assert response.json()=={'environment_id':'public-env-key','api_url':'https://flags.example.test/api/v1/','events_url':'https://events.example.test/'}
        assert all(secret not in response.text for secret in ('private-test-value','private-api-value','private-mail-value'))


def test_unconfigured_experiment_has_no_keys(tmp_path):
    config=Settings(database_url=f'sqlite:///{tmp_path}/empty.db',flagsmith_environment_id='',flagsmith_api_url='',flagsmith_events_url='')
    with TestClient(create_app(config),base_url='https://testserver') as client:
        assert client.get('/api/experiment/config').json()=={'environment_id':'','api_url':None,'events_url':None}
