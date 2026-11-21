"""Unit tests must never authenticate against configured personal mailboxes."""
import pytest
from backend.app.config import get_settings

@pytest.fixture(autouse=True)
def offline_settings(monkeypatch):
    for key in ('OPENAI_API_KEY','USER_EMAIL','USER_EMAIL_APP_PASSWORD','DEMO_COMPANY_EMAIL','DEMO_COMPANY_APP_PASSWORD'):
        monkeypatch.setenv(key,'')
    monkeypatch.setenv('REPLAY_MODE','true')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
