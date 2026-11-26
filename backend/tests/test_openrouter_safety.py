import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, SecretStr

from backend.app.ai import client, transcribe


class Result(BaseModel):
    answer: str


def test_free_provider_refuses_paid_model_and_search(monkeypatch, tmp_path):
    monkeypatch.setattr(client, 'ROOT', tmp_path)
    monkeypatch.setattr(client, 'get_settings', lambda: SimpleNamespace(llm_provider='openrouter', openrouter_api_key=SecretStr('test')))
    with pytest.raises(ValueError, match='only openrouter/free'):
        asyncio.run(client.call_structured('test', 'paid/model', Result, 'instructions', 'text'))
    with pytest.raises(ValueError, match='Web search is unavailable'):
        asyncio.run(client.call_structured('test', 'openrouter/free', Result, 'instructions', 'text', search_domains=['example.com']))


def test_free_provider_never_uses_paid_transcription(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe, 'get_settings', lambda: SimpleNamespace(llm_provider='openrouter'))
    with pytest.raises(ValueError, match='Voice transcription is unavailable'):
        asyncio.run(transcribe.transcribe(tmp_path / 'audio.wav'))
