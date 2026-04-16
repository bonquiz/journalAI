"""Set required env vars at conftest import time so `from app.config import settings`
always finds a valid instance, whether invoked via pytest or direct import."""
import os
import tempfile

# Idempotent: only set if missing, so production-like envs still win.
os.environ.setdefault("APP_PASSWORD", "testpw")
os.environ.setdefault("DB_ENCRYPTION_KEY", "a" * 64)
os.environ.setdefault("SESSION_SECRET", "b" * 64)
os.environ.setdefault("SECRET_KEY_WRAP", "c" * 64)
os.environ.setdefault("DOMAIN", "localhost")
# DB_PATH must be a per-session tempdir so test DBs are isolated and cleaned.
if "DB_PATH" not in os.environ:
    os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="journalai-test-"), "test.db")

# pytest still needs a fixture interface for individual tests that want to override:
import pytest

@pytest.fixture
def override_env(monkeypatch):
    """Use in tests that need to set a different DB_ENCRYPTION_KEY, etc."""
    return monkeypatch
