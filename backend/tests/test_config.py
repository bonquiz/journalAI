import pytest
from app.config import Settings


def test_settings_loads_from_env():
    # conftest already set valid env vars; constructing Settings() must work.
    s = Settings()
    assert s.app_password == "testpw"
    assert s.session_idle_minutes == 10
    assert s.session_absolute_hours == 12
    assert s.max_upload_mb == 25


def test_settings_requires_secrets(monkeypatch):
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    with pytest.raises(Exception):
        Settings()


def test_settings_rejects_short_hex(monkeypatch):
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "a" * 30)
    with pytest.raises(Exception):
        Settings()


def test_settings_rejects_non_hex(monkeypatch):
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "z" * 64)
    with pytest.raises(Exception):
        Settings()
