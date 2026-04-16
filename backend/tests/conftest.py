import pytest

@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_PASSWORD", "testpw")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    monkeypatch.setenv("SECRET_KEY_WRAP", "c" * 64)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DOMAIN", "localhost")
    yield
