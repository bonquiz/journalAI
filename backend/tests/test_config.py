import pytest

from app.config import Settings


def test_settings_loads_from_env():
    # conftest already set valid env vars; constructing Settings() must work.
    s = Settings()
    assert s.app_password == "test-only-seed-password"
    assert s.session_idle_minutes == 20
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


def test_settings_rejects_short_app_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "short")
    with pytest.raises(Exception, match="at least 12 characters"):
        Settings()


@pytest.mark.parametrize("banned", ["CHANGE_ME", "changeme", "password", "admin", "testpw"])
def test_settings_rejects_banned_app_password(monkeypatch, banned):
    monkeypatch.setenv("APP_PASSWORD", banned)
    with pytest.raises(Exception, match="banned-default"):
        Settings()
