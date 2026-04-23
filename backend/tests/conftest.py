"""Set required env vars at conftest import time so `from app.config import settings`
always finds a valid instance, whether invoked via pytest or direct import."""
import os
import tempfile

# Idempotent: only set if missing, so production-like envs still win.
os.environ.setdefault("APP_PASSWORD", "test-only-seed-password")
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


@pytest.fixture(autouse=True)
def _reset_embedding_worker_state():
    """Reset embedding worker state BEFORE each test to avoid event loop conflicts.

    The embedding worker uses asyncio.Event which is bound to a specific event loop.
    Each TestClient creates a new loop, so we must reset the worker between tests.
    Running this before the test ensures a clean slate.
    """
    try:
        from app.services import embedding_jobs
        # Clean up state from previous test
        embedding_jobs._state.wakeup = None
        embedding_jobs._worker_task = None
        embedding_jobs._state.pending_backfill = False
        embedding_jobs._state.pending_reindex = False
        embedding_jobs._state.running = False
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """slowapi keeps in-memory counters across tests; reset between each test."""
    try:
        from app.security.rate_limit import limiter
        limiter.reset()
    except Exception:
        pass
    yield




