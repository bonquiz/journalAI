# journalAI Phase 1 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted, single-user journal web app: voice or text entry → LLM-structured chat dialog → stored entry with title, content, tags, date. Browse / filter / edit entries. Ships as a three-container Docker stack (Caddy + SvelteKit + FastAPI) with SQLite/SQLCipher storage and OpenAI-compatible endpoints for STT and chat.

**Architecture:** Monorepo. FastAPI backend with SQLAlchemy/Alembic on SQLCipher-encrypted SQLite. SvelteKit frontend (static adapter) served via Nginx. Caddy terminates HTTPS and routes `/api/*` to backend. Every external AI call (STT, chat, embeddings later, TTS later) goes through a thin OpenAI-SDK wrapper with per-capability base URL / key / model, overridable via DB-stored settings.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, argon2-cffi, pyotp, pysqlcipher3, openai SDK, slowapi, pytest, respx. SvelteKit 2 + Svelte 5, TypeScript, Vitest, Playwright. Nginx (alpine), Caddy 2, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-04-14-journal-app-phase1-mvp-design.md`

---

## File Structure

```
journalAI/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI app + middleware stack
│   │   ├── config.py              # Pydantic Settings
│   │   ├── db.py                  # SQLCipher engine, Session factory
│   │   ├── crypto.py              # API-key wrap/unwrap (Fernet over SECRET_KEY_WRAP)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── entry.py
│   │   │   ├── tag.py
│   │   │   ├── settings.py
│   │   │   └── session.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── password.py        # argon2
│   │   │   ├── sessions.py        # create/verify/refresh/invalidate
│   │   │   ├── totp.py            # pyotp helpers
│   │   │   └── middleware.py      # session-cookie auth + idle timeout
│   │   ├── security/
│   │   │   ├── __init__.py
│   │   │   ├── csrf.py            # double-submit-token
│   │   │   └── rate_limit.py      # slowapi limiter config
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── llm_client.py      # build openai.OpenAI from settings row
│   │   │   ├── stt.py
│   │   │   ├── chat.py            # streaming + finalize
│   │   │   └── prompts.py         # default system prompts
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── entries.py
│   │   │   ├── tags.py
│   │   │   ├── transcribe.py
│   │   │   ├── chat.py
│   │   │   ├── settings.py
│   │   │   └── health.py
│   │   └── schemas/               # pydantic request/response models
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── entries.py
│   │       ├── settings.py
│   │       └── chat.py
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_sessions.py
│   │   ├── test_entries.py
│   │   ├── test_tags.py
│   │   ├── test_transcribe.py
│   │   ├── test_chat.py
│   │   ├── test_settings.py
│   │   └── test_csrf.py
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .dockerignore
├── frontend/
│   ├── src/
│   │   ├── app.html
│   │   ├── app.d.ts
│   │   ├── app.css
│   │   ├── routes/
│   │   │   ├── +layout.svelte
│   │   │   ├── +layout.ts
│   │   │   ├── +page.svelte                 # home
│   │   │   ├── login/+page.svelte
│   │   │   ├── new/+page.svelte
│   │   │   ├── entries/+page.svelte
│   │   │   ├── entries/[id]/+page.svelte
│   │   │   └── settings/+page.svelte
│   │   └── lib/
│   │       ├── api.ts
│   │       ├── audio.ts
│   │       ├── chat.ts                       # SSE
│   │       ├── stores/
│   │       │   ├── session.ts
│   │       │   └── chatDraft.ts
│   │       └── components/
│   │           ├── TextOrVoiceInput.svelte
│   │           ├── RecordButton.svelte
│   │           ├── ChatMessage.svelte
│   │           ├── EntryCard.svelte
│   │           ├── TagChip.svelte
│   │           ├── SessionCountdown.svelte
│   │           └── PreviewModal.svelte
│   ├── static/
│   │   ├── manifest.webmanifest
│   │   ├── favicon.png
│   │   └── icon-512.png
│   ├── tests/
│   │   ├── unit/                             # Vitest
│   │   └── e2e/                              # Playwright
│   ├── svelte.config.js
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   ├── playwright.config.ts
│   ├── nginx.conf
│   ├── Dockerfile
│   └── .dockerignore
├── deploy/
│   ├── docker-compose.yml
│   ├── Caddyfile
│   └── .env.example
├── .github/
│   └── workflows/
│       ├── backend-test.yml
│       ├── frontend-test.yml
│       └── build.yml
├── docs/
│   ├── superpowers/specs/
│   ├── superpowers/plans/
│   ├── endpoint-compatibility.md
│   ├── hardware-profiles.md
│   └── self-hosting.md
├── .gitignore
├── LICENSE                                   # MIT
└── README.md
```

---

### Task 1: Monorepo scaffolding and top-level docs

**Files:**
- Create: `LICENSE`, `README.md`, `docs/endpoint-compatibility.md`, `docs/hardware-profiles.md`, `docs/self-hosting.md`

- [ ] **Step 1: Create LICENSE**

Create `LICENSE` with the MIT license text, year `2026`, holder `journalAI contributors`.

- [ ] **Step 2: Create README.md**

```markdown
# journalAI

Self-hosted, open-source, single-user voice/text journal with LLM-assisted structuring.
OpenAI-compatible endpoints for STT, chat, embeddings, TTS — run fully in the cloud,
fully locally, or mix-and-match.

## Quick Start

```bash
cp deploy/.env.example deploy/.env
# edit deploy/.env — set DOMAIN, APP_PASSWORD, DB_ENCRYPTION_KEY, SESSION_SECRET,
# SECRET_KEY_WRAP, and at minimum STT + CHAT endpoints
docker compose -f deploy/docker-compose.yml up -d
```

See:
- `docs/self-hosting.md` — full setup guide
- `docs/endpoint-compatibility.md` — which AI providers/servers work
- `docs/hardware-profiles.md` — recommended hardware for local-only setups

## Privacy

No journal data, audio, or secrets are ever committed to this repository.
Your data lives in the `./data/` Docker volume. Audio files are discarded
immediately after transcription.
```

- [ ] **Step 3: Create docs/endpoint-compatibility.md**

Fill with the compatibility matrix from spec §10, plus example `.env` snippets for the three scenarios: "all-OpenAI", "all-local", "hybrid".

- [ ] **Step 4: Create docs/hardware-profiles.md**

Fill with Minimal (RTX 3060 12GB) and Comfort (RTX 4060 Ti 16GB / M3 Pro) profiles from spec §11, including expected latencies and the note that Ollama auto-unloads models.

- [ ] **Step 5: Create docs/self-hosting.md**

Document:
- DNS setup pointing `DOMAIN` at the host
- Required `.env` variables
- How to generate `DB_ENCRYPTION_KEY`, `SESSION_SECRET`, `SECRET_KEY_WRAP` via `openssl rand -hex 32`
- First-login flow (password from `APP_PASSWORD`)
- How to change password, enable TOTP
- How to point each of the four AI endpoints at different providers

- [ ] **Step 6: Commit**

```bash
git add LICENSE README.md docs/
git commit -m "docs: add README, LICENSE, and self-hosting guides"
```

---

### Task 2: Backend project setup (pyproject.toml + tooling)

**Files:**
- Create: `backend/pyproject.toml`, `backend/.dockerignore`, `backend/app/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "journalai-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "sqlalchemy>=2.0",
    "alembic>=1.14",
    "pysqlcipher3>=1.2.0",
    "argon2-cffi>=23.1",
    "pyotp>=2.9",
    "python-multipart>=0.0.12",
    "openai>=1.54",
    "httpx>=0.27",
    "cryptography>=43.0",
    "slowapi>=0.1.9",
    "qrcode[pil]>=7.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "respx>=0.21",
    "ruff>=0.7",
    "mypy>=1.13",
    "types-qrcode",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "S", "ASYNC"]
ignore = ["S101"]  # pytest uses assert

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```

- [ ] **Step 2: Write backend/.dockerignore**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
alembic/versions/*.py
!alembic/versions/__init__.py
data/
.env
```

- [ ] **Step 3: Create empty backend/app/__init__.py**

- [ ] **Step 4: Install dev dependencies locally**

Run: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`

Expected: successful install.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/.dockerignore backend/app/__init__.py
git commit -m "feat(backend): add Python project setup and dev tooling"
```

---

### Task 3: Pydantic settings (config.py)

**Files:**
- Create: `backend/app/config.py`, `backend/tests/conftest.py`, `backend/tests/test_config.py`

- [ ] **Step 1: Write failing test tests/test_config.py**

```python
import os
import pytest
from app.config import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "pw")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("SESSION_SECRET", "b" * 64)
    monkeypatch.setenv("SECRET_KEY_WRAP", "c" * 64)
    s = Settings()
    assert s.app_password == "pw"
    assert s.session_idle_minutes == 10          # default
    assert s.session_absolute_hours == 12        # default
    assert s.max_upload_mb == 25                 # default

def test_settings_requires_secrets(monkeypatch):
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 2: Write conftest.py**

```python
import os
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
```

- [ ] **Step 3: Run test — expect fail**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: ModuleNotFoundError for `app.config`.

- [ ] **Step 4: Implement app/config.py**

```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    domain: str = "localhost"
    app_password: str
    db_encryption_key: str
    session_secret: str
    secret_key_wrap: str
    db_path: str = "/app/data/journal.db"

    session_idle_minutes: int = 10
    session_absolute_hours: int = 12
    max_upload_mb: int = 25

    stt_base_url: str = "https://api.openai.com/v1"
    stt_api_key: str = ""
    stt_model: str = "whisper-1"

    chat_base_url: str = "https://api.openai.com/v1"
    chat_api_key: str = ""
    chat_model: str = "gpt-4o-mini"

    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"

    tts_base_url: str = "https://api.openai.com/v1"
    tts_api_key: str = ""
    tts_model: str = "tts-1"

    @field_validator("db_encryption_key", "session_secret", "secret_key_wrap")
    @classmethod
    def _min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("must be at least 32 characters (use openssl rand -hex 32)")
        return v

settings = Settings()  # type: ignore[call-arg]
```

- [ ] **Step 5: Run tests — expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/tests/conftest.py backend/tests/test_config.py
git commit -m "feat(backend): add typed settings from environment"
```

---

### Task 4: Crypto helpers (API-key wrap/unwrap)

**Files:**
- Create: `backend/app/crypto.py`, `backend/tests/test_crypto.py`

- [ ] **Step 1: Write failing test**

```python
from app.crypto import wrap_secret, unwrap_secret

def test_roundtrip():
    token = wrap_secret("sk-abcdef")
    assert token != "sk-abcdef"
    assert unwrap_secret(token) == "sk-abcdef"

def test_empty_returns_empty():
    assert wrap_secret("") == ""
    assert unwrap_secret("") == ""

def test_tamper_raises():
    import pytest
    from cryptography.fernet import InvalidToken
    token = wrap_secret("sk-abcdef")
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        unwrap_secret(bad)
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && .venv/bin/pytest tests/test_crypto.py -v`

- [ ] **Step 3: Implement app/crypto.py**

```python
import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import settings

def _fernet() -> Fernet:
    # Derive a 32-byte key from SECRET_KEY_WRAP
    raw = hashlib.sha256(settings.secret_key_wrap.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))

def wrap_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()

def unwrap_secret(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/crypto.py backend/tests/test_crypto.py
git commit -m "feat(backend): add Fernet-based API-key wrap/unwrap"
```

---

### Task 5: SQLCipher database engine + Alembic bootstrap

**Files:**
- Create: `backend/app/db.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/` (dir), `backend/tests/test_db.py`

- [ ] **Step 1: Write failing test tests/test_db.py**

```python
from app.db import engine, SessionLocal
from sqlalchemy import text

def test_engine_is_encrypted(tmp_path, monkeypatch):
    # conftest already points DB_PATH at tmp_path
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE foo (id INTEGER)"))
        conn.execute(text("INSERT INTO foo VALUES (1)"))
        conn.commit()
    # Reading without the key must fail — use raw sqlite3
    import sqlite3, pytest
    raw = sqlite3.connect(str(tmp_path / "test.db"))
    with pytest.raises(sqlite3.DatabaseError):
        raw.execute("SELECT * FROM foo").fetchone()
```

- [ ] **Step 2: Run — expect fail (import error)**

- [ ] **Step 3: Implement app/db.py**

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

class Base(DeclarativeBase):
    pass

# pysqlcipher3 exposes its own dialect-safe driver via sqlite+pysqlcipher
engine = create_engine(
    f"sqlite+pysqlcipher://:{settings.db_encryption_key}@/{settings.db_path}?cipher=aes-256-cbc&kdf_iter=64000",
    future=True,
    connect_args={"check_same_thread": False},
)

@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

- [ ] **Step 4: Configure Alembic**

Run: `cd backend && .venv/bin/alembic init alembic` then edit `backend/alembic/env.py` so that:

```python
from app.config import settings
from app.db import Base
# import all models so autogenerate sees them
from app.models import entry, tag, settings as settings_model, session as session_model  # noqa

config.set_main_option(
    "sqlalchemy.url",
    f"sqlite+pysqlcipher://:{settings.db_encryption_key}@/{settings.db_path}?cipher=aes-256-cbc&kdf_iter=64000",
)
target_metadata = Base.metadata
```

(Leave the rest of the generated `env.py` as-is for online migrations.)

- [ ] **Step 5: Run — expect pass**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/alembic.ini backend/alembic/ backend/tests/test_db.py
git commit -m "feat(backend): add SQLCipher-backed engine and Alembic config"
```

---

### Task 6: Models — Entry, Tag, Settings, Session

**Files:**
- Create: `backend/app/models/__init__.py`, `entry.py`, `tag.py`, `settings.py`, `session.py`

- [ ] **Step 1: Write failing test tests/test_models.py**

```python
from datetime import date, datetime, timedelta
from app.db import engine, SessionLocal, Base
from app.models.entry import Entry
from app.models.tag import Tag, EntryTag
from app.models.session import AppSession

def setup_module():
    Base.metadata.create_all(engine)

def test_entry_tag_many_to_many():
    with SessionLocal() as s:
        t = Tag(name="test")
        e = Entry(id="e1", entry_date=date.today(), title="t", content="c")
        s.add_all([t, e, EntryTag(entry_id="e1", tag_name="test")])
        s.commit()
        fetched = s.get(Entry, "e1")
        assert {t.tag_name for t in fetched.tags} == {"test"}

def test_session_expiry_fields():
    with SessionLocal() as s:
        sess = AppSession(
            id="sid", created_at=datetime.utcnow(), last_activity_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        s.add(sess)
        s.commit()
        assert s.get(AppSession, "sid") is not None
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement models**

`backend/app/models/__init__.py`:
```python
from app.models.entry import Entry
from app.models.tag import Tag, EntryTag
from app.models.settings import AppSettings
from app.models.session import AppSession

__all__ = ["Entry", "Tag", "EntryTag", "AppSettings", "AppSession"]
```

`backend/app/models/entry.py`:
```python
from datetime import date, datetime
from sqlalchemy import String, Date, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class Entry(Base):
    __tablename__ = "entries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_transcript: Mapped[str | None] = mapped_column(Text)
    chat_history: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    tags: Mapped[list["EntryTag"]] = relationship(back_populates="entry", cascade="all, delete-orphan")
```

`backend/app/models/tag.py`:
```python
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class Tag(Base):
    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(String, primary_key=True)

class EntryTag(Base):
    __tablename__ = "entry_tags"
    entry_id: Mapped[str] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True)
    tag_name: Mapped[str] = mapped_column(ForeignKey("tags.name", ondelete="CASCADE"), primary_key=True)
    entry = relationship("Entry", back_populates="tags")
```

`backend/app/models/settings.py`:
```python
from sqlalchemy import Integer, String, CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class AppSettings(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stt_base_url: Mapped[str | None] = mapped_column(String)
    stt_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    stt_model: Mapped[str | None] = mapped_column(String)
    chat_base_url: Mapped[str | None] = mapped_column(String)
    chat_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    chat_model: Mapped[str | None] = mapped_column(String)
    embed_base_url: Mapped[str | None] = mapped_column(String)
    embed_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    embed_model: Mapped[str | None] = mapped_column(String)
    tts_base_url: Mapped[str | None] = mapped_column(String)
    tts_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    tts_model: Mapped[str | None] = mapped_column(String)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    totp_secret: Mapped[str | None] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
```

`backend/app/models/session.py`:
```python
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class AppSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Generate Alembic baseline migration**

Run: `cd backend && .venv/bin/alembic revision --autogenerate -m "baseline schema"`
Expected: new file under `backend/alembic/versions/`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/ backend/tests/test_models.py backend/alembic/versions/
git commit -m "feat(backend): add ORM models and baseline migration"
```

---

### Task 7: Password hashing (argon2)

**Files:**
- Create: `backend/app/auth/__init__.py`, `backend/app/auth/password.py`, `backend/tests/test_password.py`

- [ ] **Step 1: Write failing test**

```python
from app.auth.password import hash_password, verify_password

def test_hash_verifies():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False

def test_hash_is_random():
    assert hash_password("x") != hash_password("x")
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement**

`backend/app/auth/__init__.py`: empty

`backend/app/auth/password.py`:
```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()

def hash_password(pw: str) -> str:
    return _ph.hash(pw)

def verify_password(pw: str, h: str) -> bool:
    try:
        _ph.verify(h, pw)
        return True
    except VerifyMismatchError:
        return False
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/ backend/tests/test_password.py
git commit -m "feat(backend): add argon2 password hashing"
```

---

### Task 8: Session store and idle/absolute timeout

**Files:**
- Create: `backend/app/auth/sessions.py`, `backend/tests/test_sessions.py`

- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timedelta
from app.db import engine, Base, SessionLocal
from app.auth.sessions import create_session, touch_session, invalidate_session, get_active_session

def setup_module():
    Base.metadata.create_all(engine)

def test_create_and_touch():
    sid = create_session()
    assert get_active_session(sid) is not None
    touch_session(sid)
    assert get_active_session(sid) is not None

def test_idle_expiry(monkeypatch):
    sid = create_session()
    # Fast-forward last_activity
    with SessionLocal() as db:
        from app.models.session import AppSession
        s = db.get(AppSession, sid)
        s.last_activity_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    assert get_active_session(sid) is None

def test_invalidate():
    sid = create_session()
    invalidate_session(sid)
    assert get_active_session(sid) is None
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement app/auth/sessions.py**

```python
import secrets
from datetime import datetime, timedelta
from app.config import settings
from app.db import SessionLocal
from app.models.session import AppSession

def create_session() -> str:
    sid = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    with SessionLocal() as db:
        db.add(AppSession(
            id=sid,
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(hours=settings.session_absolute_hours),
        ))
        db.commit()
    return sid

def get_active_session(sid: str) -> AppSession | None:
    if not sid:
        return None
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        if s is None:
            return None
        now = datetime.utcnow()
        idle_limit = timedelta(minutes=settings.session_idle_minutes)
        if now - s.last_activity_at > idle_limit or now > s.expires_at:
            db.delete(s)
            db.commit()
            return None
        return s

def touch_session(sid: str) -> None:
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        if s is not None:
            s.last_activity_at = datetime.utcnow()
            db.commit()

def invalidate_session(sid: str) -> None:
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        if s is not None:
            db.delete(s)
            db.commit()

def invalidate_all() -> None:
    with SessionLocal() as db:
        db.query(AppSession).delete()
        db.commit()
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/sessions.py backend/tests/test_sessions.py
git commit -m "feat(backend): add session store with idle and absolute timeouts"
```

---

### Task 9: TOTP helpers

**Files:**
- Create: `backend/app/auth/totp.py`, `backend/tests/test_totp.py`

- [ ] **Step 1: Write failing test**

```python
from app.auth.totp import generate_secret, provisioning_uri, verify_code
import pyotp

def test_verify_valid_code():
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code) is True

def test_provisioning_uri_contains_issuer():
    uri = provisioning_uri("abc123")
    assert "journalAI" in uri
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement app/auth/totp.py**

```python
import pyotp

ISSUER = "journalAI"

def generate_secret() -> str:
    return pyotp.random_base32()

def provisioning_uri(secret: str, account: str = "journal") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)

def verify_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/totp.py backend/tests/test_totp.py
git commit -m "feat(backend): add TOTP helpers"
```

---

### Task 10: App bootstrap + session middleware

**Files:**
- Create: `backend/app/main.py`, `backend/app/auth/middleware.py`, `backend/tests/test_middleware.py`

- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine
from app.auth.sessions import create_session

def setup_module():
    Base.metadata.create_all(engine)

def test_unauthed_request_401():
    with TestClient(app) as c:
        r = c.get("/api/entries")
        assert r.status_code == 401

def test_authed_request_passes():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/entries", cookies={"session": sid})
        # Route not implemented yet → 404 is fine; just prove auth passes
        assert r.status_code != 401

def test_health_is_open():
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement middleware and app**

`backend/app/auth/middleware.py`:
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.auth.sessions import get_active_session, touch_session

OPEN_PATHS = {"/api/health", "/api/auth/login"}

class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)
        if path in OPEN_PATHS:
            return await call_next(request)
        sid = request.cookies.get("session", "")
        sess = get_active_session(sid)
        if sess is None:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        request.state.session_id = sid
        response = await call_next(request)
        touch_session(sid)
        return response
```

`backend/app/main.py`:
```python
from fastapi import FastAPI
from app.auth.middleware import SessionAuthMiddleware

app = FastAPI(title="journalAI", docs_url=None, redoc_url=None)
app.add_middleware(SessionAuthMiddleware)

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/auth/middleware.py backend/tests/test_middleware.py
git commit -m "feat(backend): add app bootstrap and session auth middleware"
```

---

### Task 11: Auth routes (login / logout / password init)

**Files:**
- Create: `backend/app/schemas/auth.py`, `backend/app/routes/__init__.py`, `backend/app/routes/auth.py`, `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("testpw")))
        db.commit()

def test_login_success():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "testpw"})
        assert r.status_code == 200
        assert "session" in r.cookies

def test_login_wrong_pw():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "bad"})
        assert r.status_code == 401

def test_logout_invalidates():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "testpw"})
        sid = r.cookies["session"]
        r2 = c.post("/api/auth/logout", cookies={"session": sid})
        assert r2.status_code == 200
        # Subsequent auth fails
        r3 = c.get("/api/entries", cookies={"session": sid})
        assert r3.status_code == 401
```

- [ ] **Step 2: Write schemas/auth.py**

```python
from pydantic import BaseModel

class LoginRequest(BaseModel):
    password: str
    totp: str | None = None
```

- [ ] **Step 3: Write routes/auth.py**

```python
from fastapi import APIRouter, HTTPException, Request, Response
from app.auth.password import verify_password
from app.auth.sessions import create_session, invalidate_session
from app.auth.totp import verify_code
from app.db import SessionLocal
from app.models.settings import AppSettings
from app.schemas.auth import LoginRequest

router = APIRouter(prefix="/api/auth")

@router.post("/login")
async def login(body: LoginRequest, response: Response):
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None or not verify_password(body.password, s.password_hash):
            raise HTTPException(401, "invalid credentials")
        if s.totp_secret:
            if not body.totp or not verify_code(s.totp_secret, body.totp):
                raise HTTPException(401, "invalid totp")
    sid = create_session()
    response.set_cookie(
        "session", sid, httponly=True, secure=True,
        samesite="strict", max_age=60 * 60 * 12, path="/",
    )
    return {"ok": True}

@router.post("/logout")
async def logout(request: Request, response: Response):
    sid = getattr(request.state, "session_id", None)
    if sid:
        invalidate_session(sid)
    response.delete_cookie("session", path="/")
    return {"ok": True}
```

- [ ] **Step 4: Register router in main.py**

Add:
```python
from app.routes.auth import router as auth_router
app.include_router(auth_router)
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ backend/app/routes/ backend/tests/test_auth_routes.py backend/app/main.py
git commit -m "feat(backend): add login/logout routes"
```

---

### Task 12: TOTP setup and confirm routes

**Files:**
- Modify: `backend/app/routes/auth.py`
- Create: `backend/tests/test_totp_routes.py`

- [ ] **Step 1: Write failing tests**

```python
import pyotp
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password
from app.auth.sessions import create_session

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), totp_secret=None))
        db.commit()

def test_setup_returns_secret_and_qr():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/auth/totp/setup", cookies={"session": sid})
        assert r.status_code == 200
        j = r.json()
        assert "secret" in j and "qr_png_base64" in j

def test_confirm_activates():
    sid = create_session()
    with TestClient(app) as c:
        setup = c.post("/api/auth/totp/setup", cookies={"session": sid}).json()
        code = pyotp.TOTP(setup["secret"]).now()
        r = c.post("/api/auth/totp/confirm",
                   json={"code": code, "secret": setup["secret"]},
                   cookies={"session": sid})
        assert r.status_code == 200
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).totp_secret is not None
```

- [ ] **Step 2: Add pending-secret container and helpers to auth.py**

Append to `backend/app/routes/auth.py`:
```python
import base64
from io import BytesIO
import qrcode
from pydantic import BaseModel
from app.auth.totp import generate_secret, provisioning_uri, verify_code

class TotpConfirm(BaseModel):
    secret: str
    code: str

@router.post("/totp/setup")
async def totp_setup():
    secret = generate_secret()
    uri = provisioning_uri(secret)
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "qr_png_base64": base64.b64encode(buf.getvalue()).decode(),
    }

@router.post("/totp/confirm")
async def totp_confirm(body: TotpConfirm):
    if not verify_code(body.secret, body.code):
        raise HTTPException(400, "invalid code")
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.totp_secret = body.secret
        db.commit()
    return {"ok": True}
```

- [ ] **Step 3: Run — expect pass**

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/auth.py backend/tests/test_totp_routes.py
git commit -m "feat(backend): add TOTP setup and confirm routes"
```

---

### Task 13: First-run bootstrap (seed settings from APP_PASSWORD)

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/app/bootstrap.py`, `backend/tests/test_bootstrap.py`

- [ ] **Step 1: Write failing test**

```python
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.bootstrap import ensure_bootstrap
from app.auth.password import verify_password

def test_bootstrap_creates_settings_row():
    Base.metadata.create_all(engine)
    ensure_bootstrap()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert s is not None
        assert verify_password("testpw", s.password_hash) is True

def test_bootstrap_is_idempotent():
    ensure_bootstrap()
    ensure_bootstrap()
    with SessionLocal() as db:
        assert db.query(AppSettings).count() == 1
```

- [ ] **Step 2: Implement bootstrap.py**

```python
from app.auth.password import hash_password
from app.config import settings
from app.db import SessionLocal, engine, Base
from app.models.settings import AppSettings
from app.services.prompts import STRUCTURE_SYSTEM_PROMPT

def ensure_bootstrap() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.get(AppSettings, 1) is not None:
            return
        db.add(AppSettings(
            id=1,
            password_hash=hash_password(settings.app_password),
            system_prompt=STRUCTURE_SYSTEM_PROMPT,
        ))
        db.commit()
```

- [ ] **Step 3: Wire into main.py**

```python
from app.bootstrap import ensure_bootstrap

@app.on_event("startup")
async def _startup() -> None:
    ensure_bootstrap()
```

(If the `prompts` module doesn't yet exist, create a placeholder `backend/app/services/prompts.py` with `STRUCTURE_SYSTEM_PROMPT = ""` for now; Task 17 will fill it in.)

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/bootstrap.py backend/app/main.py backend/app/services/ backend/tests/test_bootstrap.py
git commit -m "feat(backend): add idempotent first-run bootstrap"
```

---

### Task 14: CSRF double-submit-token middleware

**Files:**
- Create: `backend/app/security/__init__.py`, `backend/app/security/csrf.py`, `backend/tests/test_csrf.py`
- Modify: `backend/app/main.py`, `backend/app/routes/auth.py`

- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.auth.sessions import create_session
from app.db import Base, engine

def setup_module():
    Base.metadata.create_all(engine)

def test_post_without_csrf_is_403():
    sid = create_session()
    with TestClient(app) as c:
        # Any POST that is not /auth/login
        r = c.post("/api/auth/logout", cookies={"session": sid})
        assert r.status_code == 403

def test_post_with_matching_header_and_cookie_passes():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/logout",
            cookies={"session": sid, "csrf": "token123"},
            headers={"X-CSRF-Token": "token123"},
        )
        assert r.status_code == 200
```

- [ ] **Step 2: Implement app/security/csrf.py**

```python
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

CSRF_EXEMPT = {"/api/auth/login", "/api/health"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") or request.method not in WRITE_METHODS or path in CSRF_EXEMPT:
            response = await call_next(request)
            if path == "/api/auth/login" and response.status_code == 200:
                response.set_cookie(
                    "csrf", secrets.token_urlsafe(32),
                    httponly=False, secure=True, samesite="strict", path="/",
                )
            return response
        cookie = request.cookies.get("csrf", "")
        header = request.headers.get("x-csrf-token", "")
        if not cookie or not header or not secrets.compare_digest(cookie, header):
            return JSONResponse({"detail": "csrf"}, status_code=403)
        return await call_next(request)
```

- [ ] **Step 3: Wire into main.py (add before SessionAuthMiddleware)**

```python
from app.security.csrf import CsrfMiddleware
app.add_middleware(CsrfMiddleware)
```

Order note: Starlette applies middleware bottom-up, so CSRF must be *added after* SessionAuth so it runs first.

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/ backend/tests/test_csrf.py backend/app/main.py
git commit -m "feat(backend): add CSRF double-submit-token middleware"
```

---

### Task 15: Rate limits on login and transcribe

**Files:**
- Create: `backend/app/security/rate_limit.py`
- Modify: `backend/app/main.py`, `backend/app/routes/auth.py`, `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Implement security/rate_limit.py**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address, default_limits=[])
```

- [ ] **Step 2: Wire into main.py**

```python
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.security.rate_limit import limiter

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def _rl(_r, _e):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": "rate_limited"}, status_code=429)
```

- [ ] **Step 3: Decorate `/auth/login`**

In `routes/auth.py`:
```python
from app.security.rate_limit import limiter
...
@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, response: Response):
    ...
```

(slowapi requires `request: Request` as first param.)

- [ ] **Step 4: Add regression test for 429**

Append to `test_auth_routes.py`:
```python
def test_login_rate_limited():
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        for _ in range(6):
            r = c.post("/api/auth/login", json={"password": "bad"})
        assert r.status_code == 429
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add backend/app/security/rate_limit.py backend/app/main.py backend/app/routes/auth.py backend/tests/test_auth_routes.py
git commit -m "feat(backend): rate-limit login attempts"
```

---

### Task 16: LLM client factory

**Files:**
- Create: `backend/app/services/llm_client.py`, `backend/tests/test_llm_client.py`

- [ ] **Step 1: Write failing test**

```python
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password
from app.crypto import wrap_secret
from app.services.llm_client import get_client

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(
            id=1, password_hash=hash_password("pw"),
            chat_base_url="https://example.test/v1",
            chat_api_key_wrapped=wrap_secret("sk-test"),
            chat_model="gpt-test",
        ))
        db.commit()

def test_chat_client_uses_db_settings():
    client, model = get_client("chat")
    assert str(client.base_url).startswith("https://example.test/v1")
    assert client.api_key == "sk-test"
    assert model == "gpt-test"

def test_fallback_to_env(monkeypatch):
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.stt_base_url = None; s.stt_api_key_wrapped = None; s.stt_model = None
        db.commit()
    client, model = get_client("stt")
    assert "openai.com" in str(client.base_url)
    assert model == "whisper-1"
```

- [ ] **Step 2: Implement services/llm_client.py**

```python
from typing import Literal
from openai import OpenAI
from app.config import settings as env
from app.crypto import unwrap_secret
from app.db import SessionLocal
from app.models.settings import AppSettings

Capability = Literal["stt", "chat", "embed", "tts"]

_DEFAULTS = {
    "stt":   (env.stt_base_url,   env.stt_api_key,   env.stt_model),
    "chat":  (env.chat_base_url,  env.chat_api_key,  env.chat_model),
    "embed": (env.embed_base_url, env.embed_api_key, env.embed_model),
    "tts":   (env.tts_base_url,   env.tts_api_key,   env.tts_model),
}

def _db_override(cap: Capability) -> tuple[str | None, str | None, str | None]:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None:
            return (None, None, None)
        key_wrapped = getattr(s, f"{cap}_api_key_wrapped")
        return (
            getattr(s, f"{cap}_base_url"),
            unwrap_secret(key_wrapped) if key_wrapped else None,
            getattr(s, f"{cap}_model"),
        )

def get_client(cap: Capability) -> tuple[OpenAI, str]:
    base_url, api_key, model = _db_override(cap)
    d_url, d_key, d_model = _DEFAULTS[cap]
    base_url = base_url or d_url
    api_key = api_key or d_key or "unused"   # local servers often require any non-empty string
    model = model or d_model
    return OpenAI(base_url=base_url, api_key=api_key), model
```

- [ ] **Step 3: Run — expect pass**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/llm_client.py backend/tests/test_llm_client.py
git commit -m "feat(backend): add per-capability OpenAI-compatible client factory"
```

---

### Task 17: Default prompts module

**Files:**
- Modify: `backend/app/services/prompts.py`

- [ ] **Step 1: Replace placeholder prompts.py with final content**

```python
STRUCTURE_SYSTEM_PROMPT = """Du bist ein Assistent, der dem Nutzer hilft,
Tagebucheinträge klar zu strukturieren, ohne Inhalte zu verfälschen oder hinzuzufügen.

Regeln:
- Arbeite ausschließlich mit dem, was der Nutzer gesagt hat.
- Keine Fakten, Gefühle oder Interpretationen erfinden.
- Korrigiere Füllwörter, Grammatik und Rechtschreibung.
- Gliedere in sinnvolle Absätze; Markdown erlaubt.
- Bewahre den Ton und die Ich-Perspektive des Nutzers.

In deiner ersten Antwort:
1. Gib den strukturierten Textentwurf zurück.
2. Stelle 1-3 kurze, offene Reflexionsfragen, die dem Nutzer helfen könnten, den Eintrag zu vertiefen. Keine Vorgaben, keine Wertungen.

Bei Folgenachrichten: Aktualisiere den Entwurf basierend auf der neuen Eingabe des Nutzers und stelle ggf. eine weitere Frage. Höre auf zu fragen, wenn der Nutzer signalisiert, dass er fertig ist."""

FINALIZE_SYSTEM_PROMPT = """Fasse den bisherigen Dialog in einen finalen Tagebucheintrag zusammen.
Gib AUSSCHLIESSLICH JSON zurück, das folgendem Schema entspricht:

{{
  "title": "<prägnanter Titel, max. 80 Zeichen>",
  "content": "<vollständiger Eintrag in Markdown, Ich-Perspektive, Ton bewahrt>",
  "tags": ["<3-7 Schlagwörter, kleingeschrieben, keine Duplikate>"],
  "entry_date": "<YYYY-MM-DD, Standardwert: heute>"
}}

Verwende bevorzugt bereits existierende Tags, wenn sinnvoll: {existing_tags}.
Wenn der Nutzer ein explizites Datum erwähnt hat, nutze es.
Erfinde keine Inhalte, die im Dialog nicht vorkamen."""
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/prompts.py
git commit -m "feat(backend): add default structure and finalize prompts"
```

---

### Task 18: STT service and /api/transcribe route

**Files:**
- Create: `backend/app/services/stt.py`, `backend/app/routes/transcribe.py`, `backend/tests/test_transcribe.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

```python
import io
import respx
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password
from app.auth.sessions import create_session

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()

def test_transcribe_returns_text():
    sid = create_session()
    audio = io.BytesIO(b"\x00\x00RIFF...fake wav...")
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "hallo welt"})
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/transcribe",
                files={"file": ("a.wav", audio, "audio/wav")},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
        assert r.status_code == 200
        assert r.json()["transcript"] == "hallo welt"
```

- [ ] **Step 2: Implement services/stt.py**

```python
from app.services.llm_client import get_client

def transcribe(audio_bytes: bytes, filename: str) -> str:
    client, model = get_client("stt")
    resp = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=model,
    )
    return resp.text
```

- [ ] **Step 3: Implement routes/transcribe.py**

```python
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from app.config import settings as env
from app.security.rate_limit import limiter
from app.services.stt import transcribe

router = APIRouter(prefix="/api")

@router.post("/transcribe")
@limiter.limit("20/minute")
async def transcribe_endpoint(request: Request, file: UploadFile = File(...)):
    max_bytes = env.max_upload_mb * 1024 * 1024
    audio = await file.read()
    if len(audio) > max_bytes:
        raise HTTPException(413, "file too large")
    text = transcribe(audio, file.filename or "audio.webm")
    # Audio is deliberately not persisted
    return {"transcript": text}
```

- [ ] **Step 4: Register router and run**

In main.py: `app.include_router(transcribe_router)`.
Run tests. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stt.py backend/app/routes/transcribe.py backend/tests/test_transcribe.py backend/app/main.py
git commit -m "feat(backend): add /transcribe route using OpenAI-compatible STT"
```

---

### Task 19: Chat streaming route (SSE)

**Files:**
- Create: `backend/app/services/chat.py`, `backend/app/routes/chat.py`, `backend/app/schemas/chat.py`, `backend/tests/test_chat.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

```python
import respx, httpx, json
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password
from app.auth.sessions import create_session

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), system_prompt="SYS"))
        db.commit()

def _sse(chunks):
    body = ""
    for c in chunks:
        body += "data: " + json.dumps(c) + "\n\n"
    body += "data: [DONE]\n\n"
    return body

def test_chat_streams_tokens():
    sid = create_session()
    sse_body = _sse([
        {"choices": [{"delta": {"content": "Hi"}}]},
        {"choices": [{"delta": {"content": " there"}}]},
    ])
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, text=sse_body,
                                        headers={"content-type": "text/event-stream"})
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
        assert r.status_code == 200
        assert "Hi" in r.text and "there" in r.text
```

- [ ] **Step 2: Write schemas/chat.py**

```python
from pydantic import BaseModel
from typing import Literal

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    system_prompt_override: str | None = None

class FinalizeRequest(BaseModel):
    messages: list[ChatMessage]
```

- [ ] **Step 3: Implement services/chat.py**

```python
from collections.abc import Iterator
from app.db import SessionLocal
from app.models.settings import AppSettings
from app.services.llm_client import get_client
from app.services.prompts import STRUCTURE_SYSTEM_PROMPT

def _system_prompt(override: str | None) -> str:
    if override:
        return override
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        return (s.system_prompt if s and s.system_prompt else STRUCTURE_SYSTEM_PROMPT)

def stream_chat(messages: list[dict], system_prompt_override: str | None = None) -> Iterator[str]:
    client, model = get_client("chat")
    sys_msg = {"role": "system", "content": _system_prompt(system_prompt_override)}
    stream = client.chat.completions.create(
        model=model, messages=[sys_msg] + messages, stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta
```

- [ ] **Step 4: Implement routes/chat.py**

```python
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest
from app.security.rate_limit import limiter
from app.services.chat import stream_chat

router = APIRouter(prefix="/api")

@router.post("/chat")
@limiter.limit("60/minute")
async def chat(request: Request, body: ChatRequest):
    def iter_sse():
        for tok in stream_chat(
            [m.model_dump() for m in body.messages],
            body.system_prompt_override,
        ):
            yield f"data: {tok}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(iter_sse(), media_type="text/event-stream")
```

- [ ] **Step 5: Register router, run tests, commit**

```bash
git add backend/app/services/chat.py backend/app/routes/chat.py backend/app/schemas/chat.py backend/tests/test_chat.py backend/app/main.py
git commit -m "feat(backend): add streaming /chat route (SSE)"
```

---

### Task 20: /api/chat/finalize route

**Files:**
- Modify: `backend/app/services/chat.py`, `backend/app/routes/chat.py`
- Create: `backend/tests/test_finalize.py`

- [ ] **Step 1: Write failing test**

```python
import respx, httpx, json
from fastapi.testclient import TestClient
from app.main import app
from app.auth.sessions import create_session
from app.db import Base, engine, SessionLocal
from app.models.tag import Tag

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(Tag(name="reise"))
        db.commit()

def test_finalize_returns_structured_json():
    sid = create_session()
    finalize_json = {
        "choices": [{"message": {"content": json.dumps({
            "title": "Test", "content": "hallo", "tags": ["reise"], "entry_date": "2026-04-14"
        })}}]
    }
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(return_value=httpx.Response(200, json=finalize_json))
        with TestClient(app) as c:
            r = c.post(
                "/api/chat/finalize",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Test"
        assert data["tags"] == ["reise"]
```

- [ ] **Step 2: Append to services/chat.py**

```python
import json
from datetime import date
from app.services.prompts import FINALIZE_SYSTEM_PROMPT
from app.models.tag import Tag

def _existing_tags() -> list[str]:
    with SessionLocal() as db:
        return [t.name for t in db.query(Tag).all()]

def finalize(messages: list[dict]) -> dict:
    client, model = get_client("chat")
    system = FINALIZE_SYSTEM_PROMPT.format(existing_tags=_existing_tags())
    def _call(extra_hint: str = ""):
        msgs = [{"role": "system", "content": system + extra_hint}] + messages
        resp = client.chat.completions.create(
            model=model, messages=msgs,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"
    raw = _call()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = json.loads(_call("\n\nAntworte ausschließlich mit validem JSON."))
    obj.setdefault("entry_date", date.today().isoformat())
    return obj
```

- [ ] **Step 3: Append to routes/chat.py**

```python
from app.schemas.chat import FinalizeRequest
from app.services.chat import finalize

@router.post("/chat/finalize")
@limiter.limit("30/minute")
async def chat_finalize(request: Request, body: FinalizeRequest):
    return finalize([m.model_dump() for m in body.messages])
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat.py backend/app/routes/chat.py backend/tests/test_finalize.py
git commit -m "feat(backend): add /chat/finalize with JSON-mode + auto-retry"
```

---

### Task 21: Entries CRUD

**Files:**
- Create: `backend/app/schemas/entries.py`, `backend/app/routes/entries.py`, `backend/tests/test_entries.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write schemas/entries.py**

```python
from datetime import date, datetime
from pydantic import BaseModel, Field
import uuid

class EntryCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    tags: list[str] = []
    entry_date: date
    raw_transcript: str | None = None
    chat_history: list[dict] | None = None

class EntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    entry_date: date | None = None

class EntryOut(BaseModel):
    id: str
    entry_date: date
    title: str
    content: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

class EntryDetail(EntryOut):
    raw_transcript: str | None
    chat_history: list[dict] | None

def new_id() -> str:
    return str(uuid.uuid4())
```

- [ ] **Step 2: Write failing test tests/test_entries.py**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password
from app.auth.sessions import create_session

HEADERS = {"x-csrf-token": "t"}
def cookies(sid): return {"session": sid, "csrf": "t"}

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()

def _create(c, sid, **overrides):
    body = {"title": "T", "content": "C", "tags": ["a"], "entry_date": "2026-04-14"}
    body.update(overrides)
    return c.post("/api/entries", json=body, cookies=cookies(sid), headers=HEADERS)

def test_create_list_get_update_delete():
    sid = create_session()
    with TestClient(app) as c:
        r = _create(c, sid)
        assert r.status_code == 201
        eid = r.json()["id"]
        assert c.get("/api/entries", cookies=cookies(sid)).json()["items"][0]["id"] == eid
        assert c.get(f"/api/entries/{eid}", cookies=cookies(sid)).json()["tags"] == ["a"]
        r2 = c.put(f"/api/entries/{eid}", json={"title": "T2"},
                   cookies=cookies(sid), headers=HEADERS)
        assert r2.status_code == 200 and r2.json()["title"] == "T2"
        assert c.delete(f"/api/entries/{eid}", cookies=cookies(sid), headers=HEADERS).status_code == 204

def test_filter_by_tag():
    sid = create_session()
    with TestClient(app) as c:
        _create(c, sid, tags=["x"]); _create(c, sid, tags=["y"])
        items = c.get("/api/entries?tags=x", cookies=cookies(sid)).json()["items"]
        assert all("x" in i["tags"] for i in items)
```

- [ ] **Step 3: Implement routes/entries.py**

```python
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from app.db import SessionLocal
from app.models.entry import Entry
from app.models.tag import Tag, EntryTag
from app.schemas.entries import EntryCreate, EntryUpdate, EntryOut, EntryDetail, new_id

router = APIRouter(prefix="/api/entries")

def _ensure_tags(db, names: list[str]) -> None:
    for n in names:
        if db.get(Tag, n) is None:
            db.add(Tag(name=n))

def _tag_names(e: Entry) -> list[str]:
    return sorted({t.tag_name for t in e.tags})

def _to_detail(e: Entry) -> dict:
    return EntryDetail(
        id=e.id, entry_date=e.entry_date, title=e.title, content=e.content,
        tags=_tag_names(e), created_at=e.created_at, updated_at=e.updated_at,
        raw_transcript=e.raw_transcript,
        chat_history=json.loads(e.chat_history) if e.chat_history else None,
    ).model_dump(mode="json")

@router.post("", status_code=201)
async def create_entry(body: EntryCreate):
    with SessionLocal() as db:
        e = Entry(
            id=new_id(), entry_date=body.entry_date, title=body.title,
            content=body.content, raw_transcript=body.raw_transcript,
            chat_history=json.dumps(body.chat_history) if body.chat_history else None,
        )
        db.add(e)
        _ensure_tags(db, body.tags)
        for n in set(body.tags):
            db.add(EntryTag(entry_id=e.id, tag_name=n))
        db.commit()
        db.refresh(e)
        return _to_detail(e)

@router.get("")
async def list_entries(
    tags: str = Query(default=""),
    q: str = Query(default=""),
    offset: int = 0, limit: int = 50,
):
    tag_list = [t for t in tags.split(",") if t]
    with SessionLocal() as db:
        stmt = select(Entry).order_by(Entry.entry_date.desc(), Entry.created_at.desc())
        if tag_list:
            stmt = stmt.where(Entry.id.in_(
                select(EntryTag.entry_id).where(EntryTag.tag_name.in_(tag_list))
                .group_by(EntryTag.entry_id)
                .having(__import__("sqlalchemy").func.count() == len(set(tag_list)))
            ))
        if q:
            like = f"%{q}%"
            stmt = stmt.where((Entry.title.ilike(like)) | (Entry.content.ilike(like)))
        total = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(stmt.subquery()))
        rows = db.scalars(stmt.offset(offset).limit(limit)).all()
        return {
            "total": total or 0,
            "items": [EntryOut(
                id=e.id, entry_date=e.entry_date, title=e.title,
                content=e.content, tags=_tag_names(e),
                created_at=e.created_at, updated_at=e.updated_at,
            ).model_dump(mode="json") for e in rows],
        }

@router.get("/{eid}")
async def get_entry(eid: str):
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        return _to_detail(e)

@router.put("/{eid}")
async def update_entry(eid: str, body: EntryUpdate):
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        if body.title is not None: e.title = body.title
        if body.content is not None: e.content = body.content
        if body.entry_date is not None: e.entry_date = body.entry_date
        if body.tags is not None:
            db.query(EntryTag).filter(EntryTag.entry_id == eid).delete()
            _ensure_tags(db, body.tags)
            for n in set(body.tags):
                db.add(EntryTag(entry_id=eid, tag_name=n))
        e.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(e)
        return _to_detail(e)

@router.delete("/{eid}", status_code=204)
async def delete_entry(eid: str):
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        db.delete(e)
        db.commit()
        return None
```

- [ ] **Step 4: Register router, run tests, commit**

```bash
git add backend/app/schemas/entries.py backend/app/routes/entries.py backend/tests/test_entries.py backend/app/main.py
git commit -m "feat(backend): add entries CRUD with tag filter and substring search"
```

---

### Task 22: Tags route

**Files:**
- Create: `backend/app/routes/tags.py`, `backend/tests/test_tags.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.auth.sessions import create_session
from app.db import Base, engine, SessionLocal
from app.models.tag import Tag

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(Tag(name="a")); db.merge(Tag(name="b"))
        db.commit()

def test_tags_list_sorted():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/tags", cookies={"session": sid})
        assert r.json() == ["a", "b"]
```

- [ ] **Step 2: Implement routes/tags.py**

```python
from fastapi import APIRouter
from app.db import SessionLocal
from app.models.tag import Tag

router = APIRouter(prefix="/api")

@router.get("/tags")
async def list_tags():
    with SessionLocal() as db:
        return sorted(t.name for t in db.query(Tag).all())
```

- [ ] **Step 3: Register, run, commit**

```bash
git add backend/app/routes/tags.py backend/tests/test_tags.py backend/app/main.py
git commit -m "feat(backend): add /tags route"
```

---

### Task 23: Settings route (GET masked, PUT with wrap)

**Files:**
- Create: `backend/app/schemas/settings.py`, `backend/app/routes/settings.py`, `backend/tests/test_settings_routes.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app
from app.auth.sessions import create_session
from app.db import Base, engine, SessionLocal
from app.models.settings import AppSettings
from app.auth.password import hash_password
from app.crypto import unwrap_secret

HEADERS = {"x-csrf-token": "t"}
def cookies(sid): return {"session": sid, "csrf": "t"}

def setup_module():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()

def test_get_masks_keys_and_put_wraps():
    sid = create_session()
    with TestClient(app) as c:
        r = c.put("/api/settings",
                  json={"chat_api_key": "sk-verysecret1234",
                        "chat_base_url": "https://x/v1", "chat_model": "m"},
                  cookies=cookies(sid), headers=HEADERS)
        assert r.status_code == 200
        g = c.get("/api/settings", cookies=cookies(sid)).json()
        assert g["chat_api_key_masked"] == "…1234"
        assert g["chat_base_url"] == "https://x/v1"
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert unwrap_secret(s.chat_api_key_wrapped) == "sk-verysecret1234"
```

- [ ] **Step 2: Implement schemas/settings.py**

```python
from pydantic import BaseModel

class SettingsOut(BaseModel):
    stt_base_url: str | None = None; stt_api_key_masked: str | None = None; stt_model: str | None = None
    chat_base_url: str | None = None; chat_api_key_masked: str | None = None; chat_model: str | None = None
    embed_base_url: str | None = None; embed_api_key_masked: str | None = None; embed_model: str | None = None
    tts_base_url: str | None = None; tts_api_key_masked: str | None = None; tts_model: str | None = None
    system_prompt: str | None = None
    totp_enabled: bool = False

class SettingsPatch(BaseModel):
    stt_base_url: str | None = None; stt_api_key: str | None = None; stt_model: str | None = None
    chat_base_url: str | None = None; chat_api_key: str | None = None; chat_model: str | None = None
    embed_base_url: str | None = None; embed_api_key: str | None = None; embed_model: str | None = None
    tts_base_url: str | None = None; tts_api_key: str | None = None; tts_model: str | None = None
    system_prompt: str | None = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str
```

- [ ] **Step 3: Implement routes/settings.py**

```python
from fastapi import APIRouter, HTTPException
from app.auth.password import hash_password, verify_password
from app.auth.sessions import invalidate_all
from app.crypto import wrap_secret, unwrap_secret
from app.db import SessionLocal
from app.models.settings import AppSettings
from app.schemas.settings import SettingsOut, SettingsPatch, PasswordChange

router = APIRouter(prefix="/api/settings")

def _mask(wrapped: str | None) -> str | None:
    if not wrapped:
        return None
    raw = unwrap_secret(wrapped)
    return "…" + raw[-4:] if len(raw) >= 4 else "…"

@router.get("")
async def get_settings() -> SettingsOut:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        return SettingsOut(
            stt_base_url=s.stt_base_url, stt_api_key_masked=_mask(s.stt_api_key_wrapped), stt_model=s.stt_model,
            chat_base_url=s.chat_base_url, chat_api_key_masked=_mask(s.chat_api_key_wrapped), chat_model=s.chat_model,
            embed_base_url=s.embed_base_url, embed_api_key_masked=_mask(s.embed_api_key_wrapped), embed_model=s.embed_model,
            tts_base_url=s.tts_base_url, tts_api_key_masked=_mask(s.tts_api_key_wrapped), tts_model=s.tts_model,
            system_prompt=s.system_prompt,
            totp_enabled=bool(s.totp_secret),
        )

@router.put("")
async def update_settings(body: SettingsPatch):
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        data = body.model_dump(exclude_unset=True)
        for cap in ("stt", "chat", "embed", "tts"):
            if f"{cap}_base_url" in data: setattr(s, f"{cap}_base_url", data[f"{cap}_base_url"])
            if f"{cap}_api_key" in data:  setattr(s, f"{cap}_api_key_wrapped", wrap_secret(data[f"{cap}_api_key"]))
            if f"{cap}_model" in data:    setattr(s, f"{cap}_model", data[f"{cap}_model"])
        if "system_prompt" in data:
            s.system_prompt = data["system_prompt"]
        db.commit()
    return {"ok": True}

@router.post("/password")
async def change_password(body: PasswordChange):
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if not verify_password(body.old_password, s.password_hash):
            raise HTTPException(401, "wrong password")
        s.password_hash = hash_password(body.new_password)
        db.commit()
    invalidate_all()
    return {"ok": True}
```

- [ ] **Step 4: Register, run, commit**

```bash
git add backend/app/schemas/settings.py backend/app/routes/settings.py backend/tests/test_settings_routes.py backend/app/main.py
git commit -m "feat(backend): add settings get/put with wrapped keys and password change"
```

---

### Task 24: Health endpoint with reachability checks

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/app/routes/health.py`, `backend/tests/test_health.py`

- [ ] **Step 1: Implement routes/health.py**

```python
import httpx
from fastapi import APIRouter
from app.services.llm_client import get_client

router = APIRouter(prefix="/api")

async def _reachable(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(url.rstrip("/") + "/models")
            return r.status_code < 500
    except Exception:
        return False

@router.get("/health")
async def health():
    checks = {}
    for cap in ("stt", "chat", "embed", "tts"):
        client, _ = get_client(cap)
        checks[cap] = await _reachable(str(client.base_url))
    return {"status": "ok", "endpoints": checks}
```

- [ ] **Step 2: Replace the inline /api/health in main.py**

Remove the inline handler; register the new router instead.

- [ ] **Step 3: Write tests/test_health.py**

```python
import respx, httpx
from fastapi.testclient import TestClient
from app.main import app

def test_health_reports_reachability():
    with respx.mock() as mock:
        mock.get("https://api.openai.com/v1/models").mock(return_value=httpx.Response(200))
        with TestClient(app) as c:
            r = c.get("/api/health")
        assert r.status_code == 200
        j = r.json()
        assert "endpoints" in j and "chat" in j["endpoints"]
```

- [ ] **Step 4: Run, commit**

```bash
git add backend/app/routes/health.py backend/app/main.py backend/tests/test_health.py
git commit -m "feat(backend): richer /health with endpoint reachability"
```

---

### Task 25: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libsqlcipher-dev sqlcipher pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 2: Build image locally**

Run: `docker build -t journalai-backend:dev backend/`
Expected: image builds.

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat(backend): add Dockerfile with SQLCipher runtime deps"
```

---

### Task 26: Frontend scaffolding (SvelteKit)

**Files:**
- Create: `frontend/package.json`, `svelte.config.js`, `vite.config.ts`, `tsconfig.json`, `src/app.html`, `src/app.d.ts`, `src/app.css`, `src/routes/+layout.svelte`, `src/routes/+layout.ts`, `.dockerignore`

- [ ] **Step 1: Scaffold manually (so we control versions)**

`frontend/package.json`:
```json
{
  "name": "journalai-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
    "test": "vitest run",
    "test:e2e": "playwright test",
    "lint": "eslint ."
  },
  "devDependencies": {
    "@playwright/test": "^1.48",
    "@sveltejs/adapter-static": "^3.0",
    "@sveltejs/kit": "^2.7",
    "@sveltejs/vite-plugin-svelte": "^4.0",
    "@types/node": "^22",
    "eslint": "^9",
    "eslint-plugin-svelte": "^2",
    "svelte": "^5.0",
    "svelte-check": "^4.0",
    "tslib": "^2",
    "typescript": "^5.6",
    "vite": "^5.4",
    "vitest": "^2.1"
  }
}
```

`frontend/svelte.config.js`:
```js
import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({ fallback: "index.html" }),   // SPA mode
  },
};
```

`frontend/vite.config.ts`:
```ts
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
```

`frontend/tsconfig.json`:
```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": { "strict": true, "resolveJsonModule": true, "esModuleInterop": true }
}
```

`frontend/src/app.html`:
```html
<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="icon" href="/favicon.png" />
    %sveltekit.head%
  </head>
  <body>%sveltekit.body%</body>
</html>
```

`frontend/src/app.d.ts`:
```ts
declare global {
  namespace App {}
}
export {};
```

`frontend/src/app.css`: minimal reset + CSS variables for light-only theme.

`frontend/src/routes/+layout.ts`:
```ts
export const ssr = false;  // SPA — auth state is client-side
export const prerender = false;
```

`frontend/src/routes/+layout.svelte`:
```svelte
<script lang="ts">
  import "../app.css";
  import { session } from "$lib/stores/session";
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import SessionCountdown from "$lib/components/SessionCountdown.svelte";
  let { children } = $props();
  onMount(async () => { await session.refresh(); });
</script>

<header class="topbar">
  <a href="/">journalAI</a>
  {#if $session.authenticated}
    <nav>
      <a href="/entries">Einträge</a>
      <a href="/settings">Einstellungen</a>
      <SessionCountdown />
    </nav>
  {/if}
</header>

<main>{@render children()}</main>
```

`frontend/.dockerignore`:
```
node_modules
.svelte-kit
dist
build
tests
```

- [ ] **Step 2: Install + build smoke**

Run: `cd frontend && npm install && npm run check`
Expected: passes (some routes missing is fine — will be added in later tasks).

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold SvelteKit app (SPA mode)"
```

---

### Task 27: API client + session store

**Files:**
- Create: `frontend/src/lib/api.ts`, `frontend/src/lib/stores/session.ts`

- [ ] **Step 1: Implement api.ts**

```ts
type Method = "GET" | "POST" | "PUT" | "DELETE";

function getCookie(name: string): string {
  return document.cookie.split("; ").find(c => c.startsWith(name + "="))?.split("=")[1] ?? "";
}

export async function api<T = unknown>(path: string, opts: {method?: Method; body?: unknown; form?: FormData} = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = getCookie("csrf");
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { method, headers, body, credentials: "same-origin" });
  if (res.status === 401) { window.location.href = "/login"; throw new Error("unauthorized"); }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? await res.json() : (await res.text() as unknown)) as T;
}
```

- [ ] **Step 2: Implement stores/session.ts**

```ts
import { writable } from "svelte/store";

type SessionState = { authenticated: boolean; idleSecondsLeft: number };
const IDLE_LIMIT_S = 10 * 60;

function createSession() {
  const { subscribe, set, update } = writable<SessionState>({ authenticated: false, idleSecondsLeft: IDLE_LIMIT_S });
  let timer: ReturnType<typeof setInterval> | null = null;

  function start() {
    stop();
    timer = setInterval(() => {
      update(s => ({ ...s, idleSecondsLeft: Math.max(0, s.idleSecondsLeft - 1) }));
    }, 1000);
    const reset = () => update(s => s.authenticated ? { ...s, idleSecondsLeft: IDLE_LIMIT_S } : s);
    for (const ev of ["click", "keydown", "touchstart"]) document.addEventListener(ev, reset, { passive: true });
  }
  function stop() { if (timer) clearInterval(timer); timer = null; }

  return {
    subscribe,
    async refresh() {
      try { await fetch("/api/health", { credentials: "same-origin" }); } catch {}
      // Authenticated iff session cookie exists and any auth route works
      const r = await fetch("/api/tags", { credentials: "same-origin" });
      set({ authenticated: r.status === 200, idleSecondsLeft: IDLE_LIMIT_S });
      if (r.status === 200) start();
    },
    async login(password: string, totp?: string) {
      const r = await fetch("/api/auth/login", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, totp }),
      });
      if (!r.ok) throw new Error("login failed");
      set({ authenticated: true, idleSecondsLeft: IDLE_LIMIT_S });
      start();
    },
    async logout() {
      await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin",
        headers: { "X-CSRF-Token": document.cookie.split("csrf=")[1]?.split(";")[0] ?? "" } });
      stop();
      set({ authenticated: false, idleSecondsLeft: IDLE_LIMIT_S });
      window.location.href = "/login";
    },
  };
}

export const session = createSession();
```

- [ ] **Step 2a: Unit test (Vitest)**

`frontend/tests/unit/session.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { get } from "svelte/store";
import { session } from "$lib/stores/session";

describe("session store", () => {
  it("starts unauthenticated", () => {
    expect(get(session).authenticated).toBe(false);
  });
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/stores/session.ts frontend/tests/unit/session.test.ts
git commit -m "feat(frontend): add API client and session store"
```

---

### Task 28: Login page

**Files:**
- Create: `frontend/src/routes/login/+page.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { session } from "$lib/stores/session";
  import { goto } from "$app/navigation";
  let password = $state("");
  let totp = $state("");
  let error = $state<string | null>(null);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    try {
      await session.login(password, totp || undefined);
      goto("/");
    } catch { error = "Login fehlgeschlagen."; }
  }
</script>

<form onsubmit={submit}>
  <h1>Anmelden</h1>
  <label>Passwort <input type="password" bind:value={password} required /></label>
  <label>TOTP (falls aktiv) <input bind:value={totp} inputmode="numeric" /></label>
  {#if error}<p class="err">{error}</p>{/if}
  <button type="submit">Anmelden</button>
</form>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/login/
git commit -m "feat(frontend): add login page"
```

---

### Task 29: TextOrVoiceInput component

**Files:**
- Create: `frontend/src/lib/audio.ts`, `frontend/src/lib/components/RecordButton.svelte`, `frontend/src/lib/components/TextOrVoiceInput.svelte`
- Create: `frontend/tests/unit/audio.test.ts`

- [ ] **Step 1: Implement audio.ts**

```ts
export class Recorder {
  private rec: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  async start(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.rec = new MediaRecorder(stream);
    this.rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.rec.start();
  }
  async stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.rec) { resolve(new Blob()); return; }
      this.rec.onstop = () => {
        this.rec?.stream.getTracks().forEach(t => t.stop());
        resolve(new Blob(this.chunks, { type: this.rec?.mimeType ?? "audio/webm" }));
      };
      this.rec.stop();
    });
  }
}

export async function transcribe(blob: Blob): Promise<string> {
  const form = new FormData();
  form.append("file", blob, "voice.webm");
  const res = await fetch("/api/transcribe", { method: "POST", body: form,
    headers: { "X-CSRF-Token": document.cookie.split("csrf=")[1]?.split(";")[0] ?? "" },
    credentials: "same-origin" });
  if (!res.ok) throw new Error("transcribe failed");
  return (await res.json()).transcript;
}
```

- [ ] **Step 2: Implement RecordButton.svelte**

```svelte
<script lang="ts">
  import { Recorder, transcribe } from "$lib/audio";
  const { oninsert }: { oninsert: (text: string) => void } = $props();
  let rec: Recorder | null = null;
  let active = $state(false);
  let loading = $state(false);

  async function toggle() {
    if (!active) {
      rec = new Recorder(); await rec.start(); active = true;
    } else {
      active = false; loading = true;
      try {
        const blob = await rec!.stop();
        const text = await transcribe(blob);
        oninsert(text);
      } finally { loading = false; }
    }
  }
</script>

<button type="button" onclick={toggle} aria-pressed={active} disabled={loading}>
  {active ? "■ Stopp" : loading ? "…" : "● Mic"}
</button>
```

- [ ] **Step 3: Implement TextOrVoiceInput.svelte**

```svelte
<script lang="ts">
  import RecordButton from "./RecordButton.svelte";
  let { value = $bindable(""), placeholder = "", onsubmit }:
    { value?: string; placeholder?: string; onsubmit?: () => void } = $props();

  function insert(t: string) { value = value ? value + "\n" + t : t; }
  function handleKey(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") onsubmit?.();
  }
</script>

<div class="tovi">
  <textarea bind:value {placeholder} onkeydown={handleKey}></textarea>
  <RecordButton oninsert={insert} />
  {#if onsubmit}<button type="button" onclick={onsubmit}>Senden</button>{/if}
</div>
```

- [ ] **Step 4: Vitest smoke**

```ts
import { describe, it, expect } from "vitest";
import { transcribe } from "$lib/audio";
describe("audio", () => {
  it("exports transcribe", () => expect(typeof transcribe).toBe("function"));
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/audio.ts frontend/src/lib/components/ frontend/tests/unit/audio.test.ts
git commit -m "feat(frontend): add MediaRecorder helper and TextOrVoiceInput"
```

---

### Task 30: Home page

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { session } from "$lib/stores/session";
  import { goto } from "$app/navigation";
  if (typeof window !== "undefined" && !$session.authenticated) goto("/login");
</script>

<section class="home">
  <a class="big" href="/new">Eintrag erfassen</a>
  <a class="big" href="/entries">Einträge ansehen</a>
</section>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(frontend): add home page with two primary actions"
```

---

### Task 31: /new chat flow

**Files:**
- Create: `frontend/src/lib/chat.ts`, `frontend/src/lib/stores/chatDraft.ts`, `frontend/src/lib/components/ChatMessage.svelte`, `frontend/src/lib/components/PreviewModal.svelte`, `frontend/src/routes/new/+page.svelte`

- [ ] **Step 1: Implement chat.ts (SSE streaming)**

```ts
export async function* streamChat(messages: {role: string, content: string}[]): AsyncGenerator<string> {
  const res = await fetch("/api/chat", {
    method: "POST", credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": document.cookie.split("csrf=")[1]?.split(";")[0] ?? "",
    },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok || !res.body) throw new Error("chat failed");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const f of frames) {
      if (!f.startsWith("data: ")) continue;
      const payload = f.slice(6);
      if (payload === "[DONE]") return;
      yield payload;
    }
  }
}

export async function finalize(messages: {role: string, content: string}[]): Promise<{title: string, content: string, tags: string[], entry_date: string}> {
  const res = await fetch("/api/chat/finalize", {
    method: "POST", credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": document.cookie.split("csrf=")[1]?.split(";")[0] ?? "",
    },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error("finalize failed");
  return await res.json();
}
```

- [ ] **Step 2: Implement stores/chatDraft.ts**

```ts
import { writable } from "svelte/store";
type Msg = { role: "user" | "assistant"; content: string };
export const chatDraft = writable<Msg[]>([]);
export function resetChatDraft() { chatDraft.set([]); }
```

- [ ] **Step 3: Implement ChatMessage.svelte**

```svelte
<script lang="ts">
  const { role, content }: { role: string; content: string } = $props();
</script>
<article class={"msg " + role}>
  <header>{role === "user" ? "Du" : "Assistent"}</header>
  <div>{content}</div>
</article>
```

- [ ] **Step 4: Implement PreviewModal.svelte**

```svelte
<script lang="ts">
  import TagChip from "./TagChip.svelte";
  let { entry = $bindable(), oncancel, onconfirm }:
    { entry: {title: string, content: string, tags: string[], entry_date: string}; oncancel: () => void; onconfirm: () => void } = $props();
  let newTag = $state("");
  function addTag() {
    const t = newTag.trim().toLowerCase();
    if (t && !entry.tags.includes(t)) entry.tags = [...entry.tags, t];
    newTag = "";
  }
  function removeTag(t: string) { entry.tags = entry.tags.filter(x => x !== t); }
</script>

<div class="modal">
  <label>Datum <input type="date" bind:value={entry.entry_date} /></label>
  <label>Titel <input bind:value={entry.title} maxlength="200" /></label>
  <label>Text <textarea bind:value={entry.content} rows="10"></textarea></label>
  <div>
    {#each entry.tags as t}<TagChip name={t} onremove={() => removeTag(t)} />{/each}
    <input bind:value={newTag} onkeydown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())} placeholder="+ Tag" />
  </div>
  <footer>
    <button type="button" onclick={oncancel}>Zurück zum Chat</button>
    <button type="button" onclick={onconfirm}>So speichern</button>
  </footer>
</div>
```

- [ ] **Step 5: Implement TagChip.svelte**

```svelte
<script lang="ts">
  const { name, onremove }: { name: string; onremove?: () => void } = $props();
</script>
<span class="chip">
  {name}
  {#if onremove}<button type="button" onclick={onremove} aria-label="remove">×</button>{/if}
</span>
```

- [ ] **Step 6: Implement routes/new/+page.svelte**

```svelte
<script lang="ts">
  import TextOrVoiceInput from "$lib/components/TextOrVoiceInput.svelte";
  import ChatMessage from "$lib/components/ChatMessage.svelte";
  import PreviewModal from "$lib/components/PreviewModal.svelte";
  import { streamChat, finalize } from "$lib/chat";
  import { chatDraft, resetChatDraft } from "$lib/stores/chatDraft";
  import { api } from "$lib/api";
  import { goto } from "$app/navigation";

  let input = $state("");
  let streaming = $state(false);
  let preview = $state<{title: string, content: string, tags: string[], entry_date: string} | null>(null);

  async function send() {
    if (!input.trim() || streaming) return;
    const userMsg = { role: "user" as const, content: input };
    chatDraft.update(m => [...m, userMsg, { role: "assistant", content: "" }]);
    const msgs = $chatDraft.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
    input = "";
    streaming = true;
    try {
      for await (const tok of streamChat(msgs)) {
        chatDraft.update(m => { m[m.length - 1] = { role: "assistant", content: m[m.length - 1].content + tok }; return m; });
      }
    } finally { streaming = false; }
  }

  async function save() {
    const msgs = $chatDraft.map(m => ({ role: m.role, content: m.content }));
    preview = await finalize(msgs);
  }

  async function confirm() {
    if (!preview) return;
    const chat = $chatDraft.map(m => ({ role: m.role, content: m.content }));
    await api("/api/entries", { method: "POST", body: { ...preview, chat_history: chat } });
    resetChatDraft();
    goto("/entries");
  }
</script>

<h1>Neuer Eintrag</h1>
{#each $chatDraft as m}<ChatMessage role={m.role} content={m.content} />{/each}
<TextOrVoiceInput bind:value={input} placeholder="Diktat oder Text…" onsubmit={send} />
{#if $chatDraft.length >= 2}
  <button type="button" onclick={save} disabled={streaming}>Eintrag jetzt speichern</button>
{/if}
{#if preview}
  <PreviewModal bind:entry={preview} oncancel={() => preview = null} onconfirm={confirm} />
{/if}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/chat.ts frontend/src/lib/stores/chatDraft.ts frontend/src/lib/components/ frontend/src/routes/new/
git commit -m "feat(frontend): add chat flow with streaming, finalize, and preview"
```

---

### Task 32: /entries list with filter

**Files:**
- Create: `frontend/src/lib/components/EntryCard.svelte`, `frontend/src/routes/entries/+page.svelte`

- [ ] **Step 1: Implement EntryCard.svelte**

```svelte
<script lang="ts">
  const { e }: { e: { id: string; title: string; entry_date: string; content: string; tags: string[] } } = $props();
  const excerpt = e.content.slice(0, 150) + (e.content.length > 150 ? "…" : "");
</script>
<a href={`/entries/${e.id}`} class="card">
  <time>{e.entry_date}</time>
  <h3>{e.title}</h3>
  <p>{excerpt}</p>
  <div>{#each e.tags as t}<span class="chip">{t}</span>{/each}</div>
</a>
```

- [ ] **Step 2: Implement routes/entries/+page.svelte**

```svelte
<script lang="ts">
  import { api } from "$lib/api";
  import EntryCard from "$lib/components/EntryCard.svelte";
  import { onMount } from "svelte";

  let allTags = $state<string[]>([]);
  let activeTags = $state<Set<string>>(new Set());
  let q = $state("");
  let items = $state<any[]>([]);

  async function load() {
    const tags = Array.from(activeTags).join(",");
    const data = await api<{items: any[]}>(`/api/entries?tags=${encodeURIComponent(tags)}&q=${encodeURIComponent(q)}`);
    items = data.items;
  }
  function toggle(t: string) {
    activeTags.has(t) ? activeTags.delete(t) : activeTags.add(t);
    activeTags = new Set(activeTags);
    load();
  }
  onMount(async () => {
    allTags = await api<string[]>("/api/tags");
    await load();
  });
</script>

<h1>Einträge</h1>
<form onsubmit={(e) => { e.preventDefault(); load(); }}>
  <input bind:value={q} placeholder="Suche…" />
  <button type="submit">Suchen</button>
</form>
<div class="tags">
  {#each allTags as t}
    <button type="button" class:active={activeTags.has(t)} onclick={() => toggle(t)}>{t}</button>
  {/each}
</div>
<div class="list">{#each items as e}<EntryCard {e} />{/each}</div>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/EntryCard.svelte frontend/src/routes/entries/+page.svelte
git commit -m "feat(frontend): add entries list with tag filter and search"
```

---

### Task 33: /entries/[id] detail and edit

**Files:**
- Create: `frontend/src/routes/entries/[id]/+page.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { page } from "$app/stores";
  import { api } from "$lib/api";
  import TagChip from "$lib/components/TagChip.svelte";
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";

  let entry = $state<any>(null);
  let editing = $state(false);
  let draft = $state<any>(null);
  let newTag = $state("");

  onMount(async () => { entry = await api(`/api/entries/${$page.params.id}`); });

  function startEdit() {
    draft = JSON.parse(JSON.stringify(entry));
    editing = true;
  }
  async function save() {
    entry = await api(`/api/entries/${entry.id}`, { method: "PUT", body: {
      title: draft.title, content: draft.content, tags: draft.tags, entry_date: draft.entry_date,
    }});
    editing = false;
  }
  async function remove() {
    if (!confirm("Wirklich löschen?")) return;
    await api(`/api/entries/${entry.id}`, { method: "DELETE" });
    goto("/entries");
  }
</script>

{#if entry}
  {#if !editing}
    <article>
      <time>{entry.entry_date}</time>
      <h1>{entry.title}</h1>
      <pre>{entry.content}</pre>
      <div>{#each entry.tags as t}<TagChip name={t} />{/each}</div>
      <button onclick={startEdit}>Bearbeiten</button>
      <button onclick={remove}>Löschen</button>
    </article>
  {:else}
    <form onsubmit={(e) => { e.preventDefault(); save(); }}>
      <input type="date" bind:value={draft.entry_date} />
      <input bind:value={draft.title} />
      <textarea rows="15" bind:value={draft.content}></textarea>
      <div>
        {#each draft.tags as t}
          <TagChip name={t} onremove={() => draft.tags = draft.tags.filter(x => x !== t)} />
        {/each}
        <input bind:value={newTag}
               onkeydown={(e) => {
                 if (e.key === "Enter") { e.preventDefault();
                   const n = newTag.trim().toLowerCase();
                   if (n && !draft.tags.includes(n)) draft.tags = [...draft.tags, n];
                   newTag = "";
                 }
               }}
               placeholder="+ Tag" />
      </div>
      <button type="submit">Speichern</button>
      <button type="button" onclick={() => editing = false}>Abbrechen</button>
    </form>
  {/if}
{/if}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/entries/\[id\]/
git commit -m "feat(frontend): add entry detail and edit view"
```

---

### Task 34: /settings page

**Files:**
- Create: `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { api } from "$lib/api";
  import { onMount } from "svelte";

  let s = $state<any>(null);
  let form = $state<any>({});
  let pwOld = $state(""); let pwNew = $state("");
  let totpSetup = $state<{secret: string, qr_png_base64: string} | null>(null);
  let totpCode = $state("");
  let msg = $state("");

  onMount(async () => { s = await api("/api/settings"); });

  async function save() {
    await api("/api/settings", { method: "PUT", body: form });
    msg = "Gespeichert."; form = {}; s = await api("/api/settings");
  }
  async function changePw() {
    await api("/api/settings/password", { method: "POST", body: { old_password: pwOld, new_password: pwNew }});
    msg = "Passwort geändert. Du wirst abgemeldet."; setTimeout(() => window.location.href = "/login", 2000);
  }
  async function startTotp() { totpSetup = await api("/api/auth/totp/setup", { method: "POST" }); }
  async function confirmTotp() {
    await api("/api/auth/totp/confirm", { method: "POST", body: { secret: totpSetup!.secret, code: totpCode }});
    totpSetup = null; s = await api("/api/settings"); msg = "TOTP aktiviert.";
  }
</script>

<h1>Einstellungen</h1>
{#if msg}<p>{msg}</p>{/if}

{#if s}
  <fieldset>
    <legend>Endpoints</legend>
    {#each ["stt","chat","embed","tts"] as cap}
      <h3>{cap}</h3>
      <label>Base URL <input bind:value={form[`${cap}_base_url`]} placeholder={s[`${cap}_base_url`] ?? ""} /></label>
      <label>API Key <input type="password" bind:value={form[`${cap}_api_key`]} placeholder={s[`${cap}_api_key_masked`] ?? "-"} /></label>
      <label>Model <input bind:value={form[`${cap}_model`]} placeholder={s[`${cap}_model`] ?? ""} /></label>
    {/each}
    <label>System-Prompt <textarea bind:value={form.system_prompt} rows="8" placeholder={s.system_prompt}></textarea></label>
    <button onclick={save}>Speichern</button>
  </fieldset>

  <fieldset>
    <legend>Passwort ändern</legend>
    <input type="password" bind:value={pwOld} placeholder="Aktuell" />
    <input type="password" bind:value={pwNew} placeholder="Neu" />
    <button onclick={changePw}>Ändern</button>
  </fieldset>

  <fieldset>
    <legend>2FA (TOTP) — {s.totp_enabled ? "aktiv" : "nicht aktiv"}</legend>
    {#if !s.totp_enabled && !totpSetup}
      <button onclick={startTotp}>Einrichten</button>
    {:else if totpSetup}
      <img src={`data:image/png;base64,${totpSetup.qr_png_base64}`} alt="TOTP QR" />
      <p>Secret: <code>{totpSetup.secret}</code></p>
      <input bind:value={totpCode} placeholder="6-stelliger Code" />
      <button onclick={confirmTotp}>Aktivieren</button>
    {/if}
  </fieldset>
{/if}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/settings/
git commit -m "feat(frontend): add settings page (endpoints, password, TOTP)"
```

---

### Task 35: SessionCountdown component + idle warning

**Files:**
- Create: `frontend/src/lib/components/SessionCountdown.svelte`

- [ ] **Step 1: Implement**

```svelte
<script lang="ts">
  import { session } from "$lib/stores/session";
  import { api } from "$lib/api";
  let showWarn = $derived($session.authenticated && $session.idleSecondsLeft <= 60 && $session.idleSecondsLeft > 0);
  function fmt(s: number) {
    const m = Math.floor(s / 60), r = s % 60;
    return `${m}:${r.toString().padStart(2, "0")}`;
  }
  async function heartbeat() { await api("/api/health"); /* activity listeners reset idle */ }
</script>

{#if $session.authenticated}
  <span class="countdown" title="Automatische Abmeldung bei Inaktivität">{fmt($session.idleSecondsLeft)}</span>
{/if}
{#if showWarn}
  <div class="warn-modal">
    <p>In {$session.idleSecondsLeft} Sekunden wirst du abgemeldet.</p>
    <button onclick={heartbeat}>Aktiv bleiben</button>
  </div>
{/if}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/components/SessionCountdown.svelte
git commit -m "feat(frontend): add session countdown with 60s warning"
```

---

### Task 36: PWA manifest + service worker

**Files:**
- Create: `frontend/static/manifest.webmanifest`, `frontend/static/service-worker.js`, `frontend/static/icon-192.png`, `frontend/static/icon-512.png`
- Modify: `frontend/src/routes/+layout.svelte`

- [ ] **Step 1: Create manifest**

```json
{
  "name": "journalAI",
  "short_name": "journalAI",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#2e3a4b",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 2: Create service-worker.js**

```js
const CACHE = "journalai-v1";
const ASSETS = ["/", "/favicon.png", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;   // never cache API
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
```

- [ ] **Step 3: Register SW in +layout.svelte (inside onMount)**

```ts
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
```

- [ ] **Step 4: Generate placeholder icons**

Run any 192/512 PNG (monochrome journal glyph) and copy into `frontend/static/`. Commit the real assets.

- [ ] **Step 5: Commit**

```bash
git add frontend/static/ frontend/src/routes/+layout.svelte
git commit -m "feat(frontend): add PWA manifest and service worker"
```

---

### Task 37: E2E tests (Playwright)

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/tests/e2e/login.spec.ts`, `frontend/tests/e2e/entry-crud.spec.ts`, `frontend/tests/e2e/session-timeout.spec.ts`

- [ ] **Step 1: Playwright config**

```ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/e2e",
  webServer: {
    command: "npm run dev",
    port: 5173,
    reuseExistingServer: !process.env.CI,
  },
  use: { baseURL: "http://localhost:5173" },
});
```

- [ ] **Step 2: login.spec.ts**

```ts
import { test, expect } from "@playwright/test";
test("login + home", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', "testpw");
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL("/");
  await expect(page.getByText("Eintrag erfassen")).toBeVisible();
});
```

- [ ] **Step 3: entry-crud.spec.ts**

Text-only path (MediaRecorder isn't worth faking in E2E): type in the chat input, send, click "Eintrag jetzt speichern" (requires chat to be stubbed in dev — in CI, point backend at a tiny mock LLM via compose profile `test`, or skip in CI and tag as local-only).

```ts
import { test, expect } from "@playwright/test";
test.skip(!!process.env.CI, "needs live backend + mock LLM profile");
test("create, edit, delete entry", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', "testpw"); await page.click('button[type="submit"]');
  await page.click("text=Eintrag erfassen");
  await page.fill("textarea", "Heute war ein ruhiger Tag.");
  await page.click("text=Senden");
  await page.waitForTimeout(500);
  await page.click("text=Eintrag jetzt speichern");
  await page.click("text=So speichern");
  await expect(page).toHaveURL(/\/entries/);
});
```

- [ ] **Step 4: session-timeout.spec.ts**

```ts
import { test, expect } from "@playwright/test";
test("session countdown renders", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', "testpw"); await page.click('button[type="submit"]');
  await expect(page.locator(".countdown")).toBeVisible();
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/tests/e2e/
git commit -m "test(frontend): add Playwright E2E suite"
```

---

### Task 38: Frontend Dockerfile + nginx.conf

**Files:**
- Create: `frontend/Dockerfile`, `frontend/nginx.conf`

- [ ] **Step 1: nginx.conf**

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  location / {
    try_files $uri $uri/ /index.html;
  }
  location /service-worker.js {
    add_header Cache-Control "no-cache";
    try_files $uri =404;
  }
}
```

- [ ] **Step 2: Dockerfile**

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 3: Build**

Run: `docker build -t journalai-frontend:dev frontend/`
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf
git commit -m "feat(frontend): add Nginx-served Docker image"
```

---

### Task 39: Compose stack + Caddyfile + .env.example

**Files:**
- Create: `deploy/docker-compose.yml`, `deploy/Caddyfile`, `deploy/.env.example`

- [ ] **Step 1: .env.example**

Copy the complete block from spec §9 (all four endpoint sets + session params + secrets with `CHANGE_ME_*` placeholders and an `openssl rand -hex 32` hint in comments).

- [ ] **Step 2: Caddyfile**

```
{$DOMAIN} {
  encode gzip
  handle /api/* { reverse_proxy backend:8000 }
  handle { reverse_proxy frontend:80 }
}
```

- [ ] **Step 3: docker-compose.yml**

```yaml
name: journalai
services:
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    environment:
      DOMAIN: ${DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [frontend, backend]
    restart: unless-stopped

  backend:
    build: ../backend
    env_file: [./.env]
    volumes:
      - ../data:/app/data
    restart: unless-stopped

  frontend:
    build: ../frontend
    restart: unless-stopped

volumes:
  caddy_data: {}
  caddy_config: {}
```

- [ ] **Step 4: Smoke-test the stack**

Run:
```bash
cp deploy/.env.example deploy/.env
# fill in valid test secrets and APP_PASSWORD=testpw, DOMAIN=localhost
docker compose -f deploy/docker-compose.yml up -d --build
curl -k http://localhost/api/health
```
Expected: JSON with `"status": "ok"`.

Run: `docker compose -f deploy/docker-compose.yml down`.

- [ ] **Step 5: Commit**

```bash
git add deploy/
git commit -m "feat(deploy): add compose stack with Caddy auto-HTTPS"
```

---

### Task 40: GitHub Actions workflows

**Files:**
- Create: `.github/workflows/backend-test.yml`, `.github/workflows/frontend-test.yml`, `.github/workflows/build.yml`

- [ ] **Step 1: backend-test.yml**

```yaml
name: backend-test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: sudo apt-get update && sudo apt-get install -y libsqlcipher-dev sqlcipher pkg-config
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v --cov=app
        env:
          APP_PASSWORD: testpw
          DB_ENCRYPTION_KEY: a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0
          SESSION_SECRET: b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0
          SECRET_KEY_WRAP: c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0
```

- [ ] **Step 2: frontend-test.yml**

```yaml
name: frontend-test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci
      - run: npm run check
      - run: npm test
```

- [ ] **Step 3: build.yml**

```yaml
name: build
on: [push, pull_request]
jobs:
  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t journalai-backend:ci backend/
      - run: docker build -t journalai-frontend:ci frontend/
```

- [ ] **Step 4: Commit**

```bash
git add .github/
git commit -m "ci: add backend, frontend, and build workflows"
```

---

### Task 41: Final integration smoke test

**Files:** none (manual verification)

- [ ] **Step 1: Full stack up**

```bash
cp deploy/.env.example deploy/.env
# Edit .env: DOMAIN=localhost, APP_PASSWORD=testpw, the three hex secrets,
# and at least CHAT_API_KEY / STT_API_KEY pointing at a real provider (or local server).
docker compose -f deploy/docker-compose.yml up -d --build
```

- [ ] **Step 2: Verify flows manually**

Open `http://localhost/` in a browser:
- Log in with `testpw`.
- Click "Eintrag erfassen", type a few sentences, click Senden. Confirm assistant response streams in.
- Click "Eintrag jetzt speichern". Confirm preview modal shows title/content/tags/date.
- Click "So speichern". Confirm redirect to `/entries` and the new entry shows.
- Click the entry, edit title, save. Refresh, confirm persistence.
- Go to `/settings`, override chat model, save, create another entry, confirm the model change took effect (e.g., different response style or a provider-visible log).
- Wait 11 minutes idle. Confirm you are logged out.

- [ ] **Step 3: Teardown**

```bash
docker compose -f deploy/docker-compose.yml down
```

- [ ] **Step 4: Commit the final release tag**

```bash
git tag v0.1.0-mvp
git log --oneline | head -20
```

---

## Self-Review

**Spec coverage:**

- Architecture (§3) — Tasks 25, 38, 39
- Data model (§4) — Tasks 5, 6
- Backend modules (§5) — Tasks 3–24
- Session & auth (§5.2) — Tasks 7, 8, 9, 10, 11, 12, 14, 15
- LLM services (§5.3) — Tasks 16, 17, 18, 19, 20
- API (§5.4) — Tasks 11, 12, 18, 19, 20, 21, 22, 23, 24
- Frontend routes (§6.1) — Tasks 28, 30, 31, 32, 33, 34
- `TextOrVoiceInput` (§6.2) — Task 29
- New-Entry-Flow (§6.3) — Task 31
- Entries list / detail (§6.4) — Tasks 32, 33
- Session UI (§6.5) — Tasks 27, 35
- PWA (§6.6) — Task 36
- Prompts (§7) — Task 17
- Security (§8) — Tasks 4, 8, 14, 15
- Config (§9) — Tasks 3, 39
- Docs (§10, §11) — Task 1
- Tests (§12) — Every backend task adds tests; Tasks 27, 29 add frontend unit tests; Task 37 covers E2E; Task 40 wires CI.

No uncovered requirements.

**Placeholder scan:** clean — every step contains actual code or concrete commands. The `icon-192.png` / `icon-512.png` step relies on the implementer generating icons, which is flagged explicitly and isn't a code placeholder.

**Type consistency:** `get_client` returns `(OpenAI, str)` in Task 16 and is used the same way in Tasks 18, 19, 20, 24. `ChatRequest`, `FinalizeRequest` from Task 19 are used unchanged in Task 20. `EntryCreate`/`EntryOut`/`EntryDetail` from Task 21 are produced/consumed consistently. Session-cookie name `"session"`, CSRF-cookie name `"csrf"`, CSRF-header `X-CSRF-Token` are consistent from middleware (Task 14) through API client (Task 27) and all frontend fetches.

**Scope check:** single cohesive MVP, no subsystem overlap. Phase 2 (semantic search) and Phase 3 (TTS) are deliberately out of scope and flagged in the spec.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-journal-app-phase1-mvp.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
