import pytest
from app.config import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    monkeypatch.setenv("SECRET_KEY_WRAP", "c" * 64)
    s = Settings()
    assert s.app_password == "pw"
    assert s.session_idle_minutes == 10
    assert s.session_absolute_hours == 12
    assert s.max_upload_mb == 25

def test_settings_requires_secrets(monkeypatch):
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    with pytest.raises(Exception):
        Settings()

def test_settings_rejects_short_hex(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "a" * 30)   # too short
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    monkeypatch.setenv("SECRET_KEY_WRAP", "c" * 64)
    with pytest.raises(Exception):
        Settings()

def test_settings_rejects_non_hex(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "z" * 64)   # non-hex chars
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    monkeypatch.setenv("SECRET_KEY_WRAP", "c" * 64)
    with pytest.raises(Exception):
        Settings()
