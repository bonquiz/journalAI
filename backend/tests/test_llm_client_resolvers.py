"""Unit-Tests für die symmetrischen Resolver-Helper.

Die Helper müssen exakt dieselbe Resolution-Chain wie `get_client` verwenden:
DB-Setting → ENV → OpenAI-Default (nur für base_url = api.openai.com-Fälle).

Wir patchen `_DEFAULTS[cap]` direkt (Snapshot-Semantik bleibt erhalten).
"""
import pytest

from app.services import llm_client


def test_resolved_base_url_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("http://ollama:11434/v1", "", ""))
    assert llm_client.resolved_base_url("chat") == "http://ollama:11434/v1"


def test_resolved_base_url_db_wins_over_env(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override",
                        lambda cap: ("http://db-host/v1", None, None))
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("http://env-host/v1", "", ""))
    assert llm_client.resolved_base_url("chat") == "http://db-host/v1"


def test_resolved_api_key_returns_env_default(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("http://ollama:11434/v1", "env-key", ""))
    assert llm_client.resolved_api_key("chat") == "env-key"


def test_resolved_api_key_openai_shared_fallback(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("https://api.openai.com/v1", "", ""))
    monkeypatch.setattr(llm_client.env, "openai_api_key", "sk-shared")
    assert llm_client.resolved_api_key("chat") == "sk-shared"


def test_resolved_api_key_defaults_to_unused_for_local(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("http://ollama:11434/v1", "", ""))
    monkeypatch.setattr(llm_client.env, "openai_api_key", "")
    assert llm_client.resolved_api_key("chat") == "unused"


def test_resolved_api_key_db_wins_over_env(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override",
                        lambda cap: (None, "db-key", None))
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("http://ollama:11434/v1", "env-key", ""))
    assert llm_client.resolved_api_key("chat") == "db-key"


def test_resolved_base_url_unknown_cap_raises():
    with pytest.raises(ValueError, match="unknown capability"):
        llm_client.resolved_base_url("bogus")  # type: ignore[arg-type]


def test_resolved_api_key_unknown_cap_raises():
    with pytest.raises(ValueError, match="unknown capability"):
        llm_client.resolved_api_key("bogus")  # type: ignore[arg-type]
