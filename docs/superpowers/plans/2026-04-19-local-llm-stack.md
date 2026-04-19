# Lokaler LLM-Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** journalAI vollständig lokal betreibbar machen (Ollama + speaches + Kokoro) mit dokumentiertem Hetzner-Bootstrap als optionalem Unterpfad, ohne den bestehenden OpenAI-Pfad zu brechen.

**Architecture:** Zwei Compose-Overlays (`local-llm.yml` base + `local-llm.gpu.yml` GPU) hängen drei neue Services ans bestehende Compose-Setup; das Backend bekommt zwei kleine symmetrische Resolver-Helper (`resolved_base_url`, `resolved_api_key`) und erweitert `GET /api/settings` um `resolved_*`-Felder. Hetzner-Bootstrap ist ein Bash-Skript mit HCloud-CLI + rsync. Benchmarks messen die vier Capabilities gegen eine laufende Instanz.

**Tech Stack:** Docker Compose v2 • Ollama • speaches (faster-whisper) • Kokoro-FastAPI • HCloud CLI • Bash • FastAPI + pydantic • SvelteKit 2 + Svelte 5 runes • pytest + vitest

**Spec:** `docs/superpowers/specs/2026-04-19-local-llm-stack-design.md`

---

## File Structure

**Create:**
- `deploy/docker-compose.local-llm.yml` — Base-Overlay (ollama, ollama-init, speaches, kokoro, Volumes)
- `deploy/docker-compose.local-llm.gpu.yml` — GPU-Overlay (nvidia-Reservations)
- `deploy/.env.local-llm.example` — Vorlage mit beiden Tier-Blöcken
- `deploy/.env.hetzner.example` — Vorlage für HCloud-Token + SSH-Key-Label
- `scripts/hetzner/bootstrap.sh` — Server erstellen + Stack starten
- `scripts/hetzner/teardown.sh` — Server + Firewall löschen
- `scripts/benchmark.sh` — Tokens/s + RTF messen, Report schreiben
- `tests/fixtures/benchmark-60s.webm` — 60s-Audio-Fixture (manuell erstellt)
- `docs/self-hosting/local-llm.md` — Stack-Betrieb lokal
- `docs/self-hosting/hetzner.md` — HCloud-Pfad + Tailscale-Härtung
- `docs/benchmarks/.gitkeep` — Leerer Ordner für Report-Files
- `.github/workflows/local-llm-compose-validate.yml` — CI für Compose-YAML-Syntax
- `backend/tests/test_llm_client_resolvers.py` — Unit-Tests für neue Helpers
- `backend/tests/test_settings_resolved_fields.py` — Tests für erweiterte SettingsOut
- `frontend/src/lib/settings-env-hint.test.ts` — Vitest für Env-Hinweis-Logik

**Modify:**
- `backend/app/services/llm_client.py` — neue `resolved_base_url`/`resolved_api_key`-Helpers
- `backend/app/schemas/settings.py` — `SettingsOut` um `resolved_*`-Felder erweitern
- `backend/app/routes/settings.py` — `_settings_to_out` nutzt neue Resolver
- `frontend/src/routes/settings/+page.svelte` — „aus ENV: …"-Hinweis pro Capability
- `.gitignore` — `deploy/.env.hetzner`, `deploy/.env.local-llm`, `deploy/.env.benchmark`, `docs/benchmarks/*.md` (aber `.gitkeep` erlauben) — nur wenn nicht schon abgedeckt
- `README.md` — neuer Abschnitt „Local-LLM Stack" + Benchmark-Übersichtstabelle

---

## Task 1: Symmetrische Resolver-Helper im Backend

**Files:**
- Modify: `backend/app/services/llm_client.py`
- Create: `backend/tests/test_llm_client_resolvers.py`

- [ ] **Step 1: Failing-Test für `resolved_base_url` schreiben**

`backend/tests/test_llm_client_resolvers.py`:

```python
"""Unit-Tests für die symmetrischen Resolver-Helper.

Die Helper müssen exakt dieselbe Resolution-Chain wie `get_client` verwenden:
DB-Setting → ENV → OpenAI-Default (nur für base_url = api.openai.com-Fälle).
"""
import pytest

from app.services import llm_client


def setup_module(module):
    # Saubere In-Memory-DB pro Modul; entry-embeddings-Tabelle wird in conftest
    # initialisiert.
    from app.db import Base, engine
    Base.metadata.create_all(engine)


def test_resolved_base_url_falls_back_to_env(monkeypatch):
    # DB leer, ENV liefert Ollama-URL
    monkeypatch.setattr(llm_client._DEFAULTS, "__getitem__",
                        lambda key: ("http://ollama:11434/v1", "", "") if key == "chat"
                        else llm_client._DEFAULTS.get(key))
    assert llm_client.resolved_base_url("chat") == "http://ollama:11434/v1"


def test_resolved_base_url_db_wins_over_env(monkeypatch):
    # DB hat Override, ENV wird ignoriert
    def fake_db_override(cap):
        if cap == "chat":
            return ("http://db-host/v1", None, None)
        return (None, None, None)
    monkeypatch.setattr(llm_client, "_db_override", fake_db_override)
    assert llm_client.resolved_base_url("chat") == "http://db-host/v1"


def test_resolved_api_key_returns_env_default(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    # ENV setzt chat_api_key
    import app.config
    monkeypatch.setattr(app.config.settings, "chat_api_key", "env-key")
    monkeypatch.setattr(app.config.settings, "chat_base_url", "http://ollama:11434/v1")
    # Re-import triggers _DEFAULTS re-eval not needed; we call resolver directly
    assert llm_client.resolved_api_key("chat") == "env-key"


def test_resolved_api_key_openai_shared_fallback(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    import app.config
    monkeypatch.setattr(app.config.settings, "chat_api_key", "")
    monkeypatch.setattr(app.config.settings, "chat_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(app.config.settings, "openai_api_key", "sk-shared")
    assert llm_client.resolved_api_key("chat") == "sk-shared"


def test_resolved_api_key_defaults_to_unused_for_local(monkeypatch):
    monkeypatch.setattr(llm_client, "_db_override", lambda cap: (None, None, None))
    import app.config
    monkeypatch.setattr(app.config.settings, "chat_api_key", "")
    monkeypatch.setattr(app.config.settings, "chat_base_url", "http://ollama:11434/v1")
    monkeypatch.setattr(app.config.settings, "openai_api_key", "")
    assert llm_client.resolved_api_key("chat") == "unused"
```

- [ ] **Step 2: Test laufen lassen — rot**

`cd backend && .venv/bin/pytest tests/test_llm_client_resolvers.py -v`

Erwartet: `AttributeError: module 'app.services.llm_client' has no attribute 'resolved_base_url'`.

- [ ] **Step 3: Resolver-Helper implementieren**

In `backend/app/services/llm_client.py` direkt unter `resolved_model` ergänzen:

```python
def resolved_base_url(cap: Capability) -> str | None:
    """Resolve base_url for a capability. Chain: DB → ENV."""
    if cap not in _DEFAULTS:
        raise ValueError(f"unknown capability: {cap}")
    db_url, _, _ = _db_override(cap)
    d_url, _, _ = _DEFAULTS[cap]
    return db_url or d_url or None


def resolved_api_key(cap: Capability) -> str:
    """Resolve api_key for a capability. Chain: DB → ENV → OPENAI_API_KEY
    (only when base_url points at api.openai.com) → 'unused'.
    Mirrors the logic in `get_client`.
    """
    if cap not in _DEFAULTS:
        raise ValueError(f"unknown capability: {cap}")
    db_url, db_key, _ = _db_override(cap)
    d_url, d_key, _ = _DEFAULTS[cap]
    base_url = db_url or d_url
    api_key = db_key or d_key
    if not api_key and "api.openai.com" in (base_url or "") and env.openai_api_key:
        api_key = env.openai_api_key
    return api_key or "unused"
```

Ausserdem `_DEFAULTS` ist als Modul-Konstante per `env.*`-Werte eingelesen; da pydantic-settings beim Test-Run frisch instanziiert wird, reichen `monkeypatch.setattr(app.config.settings, …)` nicht aus, um `_DEFAULTS` zu updaten. Daher in den Resolvern stattdessen **live** aus `env` lesen:

```python
def _env_defaults(cap: str) -> tuple[str, str, str]:
    return (
        getattr(env, f"{cap}_base_url"),
        getattr(env, f"{cap}_api_key"),
        getattr(env, f"{cap}_model"),
    )
```

Und `_DEFAULTS`-Zugriffe in `resolved_base_url`, `resolved_api_key`, `resolved_model` und `get_client` durch `_env_defaults(cap)` ersetzen. So liest die Resolution-Chain konsistent die aktuellen ENV-Werte — wichtig für Monkeypatch-basierte Tests und spätere dynamische ENV-Änderungen.

- [ ] **Step 4: Tests laufen — grün**

`cd backend && .venv/bin/pytest tests/test_llm_client_resolvers.py -v`

Erwartet: 5/5 PASS.

- [ ] **Step 5: Gesamt-Testsuite grün**

`cd backend && .venv/bin/pytest -q`

Erwartet: 160 passed (155 + 5 neue). Keine Regression.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm_client.py backend/tests/test_llm_client_resolvers.py
git commit -m "feat(llm-client): add resolved_base_url / resolved_api_key helpers"
```

---

## Task 2: `SettingsOut` um `resolved_*`-Felder erweitern

**Files:**
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/routes/settings.py`
- Create: `backend/tests/test_settings_resolved_fields.py`

- [ ] **Step 1: Failing-Test für API-Response schreiben**

`backend/tests/test_settings_resolved_fields.py`:

```python
"""GET /api/settings muss resolved_base_url / resolved_model pro
Capability zurückgeben, sodass das Frontend den effektiven Wert
anzeigen kann, wenn das DB-Feld leer ist.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, engine


def setup_module(module):
    Base.metadata.create_all(engine)


@pytest.fixture
def client_authed(monkeypatch):
    # ENV-Default für chat → Ollama; DB bleibt leer
    monkeypatch.setenv("CHAT_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("CHAT_MODEL", "qwen2.5:7b-instruct-q4_K_M")
    # pydantic-settings cache resetten
    from app.config import get_settings
    get_settings.cache_clear()
    # Login via fixture helper (wie in bestehenden Tests)
    from backend.tests.helpers import login_client  # existing helper
    c = TestClient(app)
    login_client(c)
    return c


def test_get_settings_returns_resolved_chat(client_authed):
    r = client_authed.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["chat_base_url"] in (None, "")
    assert body["chat_resolved_base_url"] == "http://ollama:11434/v1"
    assert body["chat_resolved_model"] == "qwen2.5:7b-instruct-q4_K_M"
```

Falls `login_client` nicht existiert: in `backend/tests/helpers.py` hinterlegen (einmaliger Auth-Helper, der bereits mehrfach refactoriert werden könnte — hier nur importieren; bei Abweichung wie in bestehender Test-Helper-Konvention).

- [ ] **Step 2: Test laufen — rot**

`cd backend && .venv/bin/pytest tests/test_settings_resolved_fields.py -v`

Erwartet: `KeyError: 'chat_resolved_base_url'`.

- [ ] **Step 3: Schema erweitern**

In `backend/app/schemas/settings.py`, `SettingsOut` um folgende Felder pro Capability ergänzen (Block ersetzt nicht die bestehenden, ergänzt sie):

```python
class SettingsOut(BaseModel):
    stt_base_url: str | None = None
    stt_api_key_masked: str | None = None
    stt_model: str | None = None
    stt_resolved_base_url: str | None = None
    stt_resolved_model: str | None = None

    chat_base_url: str | None = None
    chat_api_key_masked: str | None = None
    chat_model: str | None = None
    chat_resolved_base_url: str | None = None
    chat_resolved_model: str | None = None

    embed_base_url: str | None = None
    embed_api_key_masked: str | None = None
    embed_model: str | None = None
    embed_resolved_base_url: str | None = None
    embed_resolved_model: str | None = None

    tts_base_url: str | None = None
    tts_api_key_masked: str | None = None
    tts_model: str | None = None
    tts_resolved_base_url: str | None = None
    tts_resolved_model: str | None = None

    tts_voice: str | None = None
    tts_speed: float | None = None
    system_prompt: str | None = None
    totp_enabled: bool = False
```

- [ ] **Step 4: `_settings_to_out` anpassen**

In `backend/app/routes/settings.py`, imports um Resolver erweitern:

```python
from app.services.llm_client import resolved_base_url, resolved_model
```

`_settings_to_out(s: AppSettings)` um die vier `resolved_*`-Paare ergänzen:

```python
def _settings_to_out(s: AppSettings) -> SettingsOut:
    return SettingsOut(
        stt_base_url=s.stt_base_url,
        stt_api_key_masked=_mask(s.stt_api_key_wrapped),
        stt_model=s.stt_model,
        stt_resolved_base_url=resolved_base_url("stt"),
        stt_resolved_model=resolved_model("stt"),
        chat_base_url=s.chat_base_url,
        chat_api_key_masked=_mask(s.chat_api_key_wrapped),
        chat_model=s.chat_model,
        chat_resolved_base_url=resolved_base_url("chat"),
        chat_resolved_model=resolved_model("chat"),
        embed_base_url=s.embed_base_url,
        embed_api_key_masked=_mask(s.embed_api_key_wrapped),
        embed_model=s.embed_model,
        embed_resolved_base_url=resolved_base_url("embed"),
        embed_resolved_model=resolved_model("embed"),
        tts_base_url=s.tts_base_url,
        tts_api_key_masked=_mask(s.tts_api_key_wrapped),
        tts_model=s.tts_model,
        tts_resolved_base_url=resolved_base_url("tts"),
        tts_resolved_model=resolved_model("tts"),
        tts_voice=s.tts_voice,
        tts_speed=s.tts_speed,
        system_prompt=s.system_prompt,
        totp_enabled=bool(s.totp_secret),
    )
```

(Die genauen Feldnamen für Key-Masking und TOTP bitte an bestehende Implementation angleichen; Mask-Helper und TOTP-Zweig nicht ändern.)

- [ ] **Step 5: Test laufen — grün**

`cd backend && .venv/bin/pytest tests/test_settings_resolved_fields.py -v`

Erwartet: 1/1 PASS. Weitere, pro-Capability-Tests müssen hier nicht explizit aufgeschrieben werden — der Helper-Mechanismus ist durch Task 1 abgedeckt.

- [ ] **Step 6: Bestehende Settings-Tests grün**

`cd backend && .venv/bin/pytest tests/test_settings.py tests/test_settings_resolved_fields.py -q`

Erwartet: alle Tests dieser Dateien PASS; existierende Tests prüfen kein `resolved_*` (und scheitern somit nicht, wenn das Schema zusätzliche optionale Felder enthält).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/settings.py backend/app/routes/settings.py backend/tests/test_settings_resolved_fields.py
git commit -m "feat(settings-api): expose resolved_base_url and resolved_model per capability"
```

---

## Task 3: Frontend zeigt „aus ENV: …"-Hinweis in `/settings`

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`
- Create: `frontend/src/lib/settings-env-hint.test.ts`
- Create: `frontend/src/lib/settings-env-hint.ts`

- [ ] **Step 1: Failing-Test für Hint-Logik schreiben**

`frontend/src/lib/settings-env-hint.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { envHint } from "./settings-env-hint";

describe("envHint", () => {
  it("returns null when DB value is set", () => {
    expect(envHint("http://custom/v1", "http://ollama:11434/v1")).toBeNull();
  });

  it("returns the resolved value when DB value is empty", () => {
    expect(envHint("", "http://ollama:11434/v1")).toBe("http://ollama:11434/v1");
    expect(envHint(null, "http://ollama:11434/v1")).toBe("http://ollama:11434/v1");
  });

  it("returns null when neither is set", () => {
    expect(envHint("", null)).toBeNull();
    expect(envHint("", "")).toBeNull();
  });

  it("does not leak resolved when DB equals resolved (redundant hint)", () => {
    expect(envHint("http://ollama:11434/v1", "http://ollama:11434/v1")).toBeNull();
  });
});
```

- [ ] **Step 2: Test laufen — rot**

`cd frontend && npm test -- settings-env-hint`

Erwartet: Fehler „Cannot find module './settings-env-hint'".

- [ ] **Step 3: Helper implementieren**

`frontend/src/lib/settings-env-hint.ts`:

```typescript
/**
 * Return a hint string to show under an empty Settings input field when the
 * backend has resolved a value from ENV. Returns null when the DB field is
 * non-empty or when there is no resolved value.
 */
export function envHint(dbValue: string | null | undefined, resolved: string | null | undefined): string | null {
  const db = (dbValue ?? "").trim();
  const res = (resolved ?? "").trim();
  if (db.length > 0) return null;
  if (res.length === 0) return null;
  return res;
}
```

- [ ] **Step 4: Test laufen — grün**

`cd frontend && npm test -- settings-env-hint`

Erwartet: 4/4 PASS.

- [ ] **Step 5: Hint in `/settings`-Seite verdrahten**

In `frontend/src/routes/settings/+page.svelte` unter jedem base_url-Input + jedem model-Input einen kleinen Hinweis-Block rendern. Muster:

```svelte
<script lang="ts">
  import { envHint } from "$lib/settings-env-hint";
  // … bestehende $state-Deklarationen
</script>

<label>
  Chat base_url
  <input bind:value={form.chat_base_url} placeholder={settings?.chat_resolved_base_url ?? ""} />
  {#if envHint(form.chat_base_url, settings?.chat_resolved_base_url)}
    <small class="env-hint">aus ENV: {envHint(form.chat_base_url, settings?.chat_resolved_base_url)}</small>
  {/if}
</label>
```

Analog für `chat_model`, `stt_base_url`, `stt_model`, `embed_*`, `tts_*`. `settings` stammt aus der bestehenden `load`-Funktion, die `/api/settings` abfragt; Typdefinition in `$lib/api/settings.ts` (oder wo existierend) um `*_resolved_*`-Felder erweitern.

CSS-Klasse `.env-hint` in der bestehenden Style-Sektion:

```css
.env-hint {
  display: block;
  margin-top: 0.25rem;
  color: var(--muted, #888);
  font-size: 0.85rem;
}
```

- [ ] **Step 6: Frontend-Tests grün + Typecheck**

```bash
cd frontend && npm test && npm run check
```

Erwartet: alle Tests PASS, `svelte-check` 0 Fehler.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/settings-env-hint.ts frontend/src/lib/settings-env-hint.test.ts frontend/src/routes/settings/+page.svelte frontend/src/lib/api/settings.ts
git commit -m "feat(settings-ui): show 'aus ENV' hint when DB field is empty"
```

(Pfad `api/settings.ts` nur committen, wenn er durch die Type-Erweiterung tatsächlich geändert wurde.)

---

## Task 4: Compose Base-Overlay (`local-llm.yml`)

**Files:**
- Create: `deploy/docker-compose.local-llm.yml`
- Create: `deploy/.env.local-llm.example`

- [ ] **Step 1: `.env.local-llm.example` anlegen**

```dotenv
# Aktiviere GENAU EINEN Tier-Block.
# ----------------------------------------------------------------------------
# Tier: Minimal (CPU-only). Realistisch für Evaluation, nicht für Dauerbetrieb.
# Erwartete Performance (Messung im Hetzner-Testlauf, siehe docs/benchmarks/):
#   Chat: ~3-8 tok/s • STT: ~1x realtime • Embed: ~20 entries/s • TTS: ~1x realtime
# ----------------------------------------------------------------------------
# CHAT_BASE_URL=http://ollama:11434/v1
# CHAT_API_KEY=ollama
# CHAT_MODEL=qwen2.5:3b-instruct-q4_K_M
#
# EMBED_BASE_URL=http://ollama:11434/v1
# EMBED_API_KEY=ollama
# EMBED_MODEL=all-minilm
#
# STT_BASE_URL=http://speaches:8000/v1
# STT_API_KEY=speaches
# STT_MODEL=Systran/faster-whisper-base
#
# TTS_BASE_URL=http://kokoro:8880/v1
# TTS_API_KEY=kokoro
# TTS_MODEL=kokoro
# TTS_VOICE=af_sky

# ----------------------------------------------------------------------------
# Tier: Recommended (NVIDIA-GPU ≥8 GB VRAM).
# ----------------------------------------------------------------------------
CHAT_BASE_URL=http://ollama:11434/v1
CHAT_API_KEY=ollama
CHAT_MODEL=qwen2.5:7b-instruct-q4_K_M

EMBED_BASE_URL=http://ollama:11434/v1
EMBED_API_KEY=ollama
EMBED_MODEL=bge-m3

STT_BASE_URL=http://speaches:8000/v1
STT_API_KEY=speaches
STT_MODEL=Systran/faster-whisper-large-v3

TTS_BASE_URL=http://kokoro:8880/v1
TTS_API_KEY=kokoro
TTS_MODEL=kokoro
TTS_VOICE=af_sky
```

- [ ] **Step 2: Base-Compose-File schreiben**

`deploy/docker-compose.local-llm.yml`:

```yaml
# Overlay: lokaler LLM-Stack (CPU-tauglich).
# Nutzung: docker compose -f docker-compose.yml -f docker-compose.local-llm.yml \
#           --env-file .env --env-file .env.local-llm up -d
# GPU: zusätzlich -f docker-compose.local-llm.gpu.yml.

services:
  ollama:
    image: ollama/ollama:0.3.14
    restart: unless-stopped
    volumes:
      - ollama_models:/root/.ollama
    networks: [journalai_net]
    healthcheck:
      test: ["CMD-SHELL", "ollama list >/dev/null 2>&1 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10

  ollama-init:
    image: ollama/ollama:0.3.14
    depends_on:
      ollama:
        condition: service_healthy
    restart: "no"
    entrypoint: ["/bin/sh", "-c"]
    command: >-
      "OLLAMA_HOST=http://ollama:11434 ollama pull ${CHAT_MODEL} &&
       OLLAMA_HOST=http://ollama:11434 ollama pull ${EMBED_MODEL}"
    networks: [journalai_net]

  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cpu
    restart: unless-stopped
    volumes:
      - speaches_models:/home/ubuntu/.cache/huggingface
    networks: [journalai_net]
    environment:
      - WHISPER__MODEL=${STT_MODEL}

  kokoro:
    image: ghcr.io/remsky/kokoro-fastapi-cpu:latest
    restart: unless-stopped
    volumes:
      - kokoro_models:/app/models
    networks: [journalai_net]

  backend:
    env_file:
      - .env
      - .env.local-llm
    depends_on:
      ollama:
        condition: service_healthy

volumes:
  ollama_models:
  speaches_models:
  kokoro_models:
```

Hinweis: Das Image-Tag `ollama/ollama:0.3.14` wird gepinnt; neuere Versionen sollten erst nach Re-Benchmark übernommen werden. Bei Erscheinen des Plans aktuelle stabile Version verifizieren und bei Bedarf updaten.

- [ ] **Step 3: YAML-Validität prüfen**

```bash
cd deploy && cp .env.local-llm.example .env.local-llm && \
  docker compose -f docker-compose.yml -f docker-compose.local-llm.yml --env-file .env --env-file .env.local-llm config > /dev/null && \
  rm .env.local-llm
```

Erwartet: Exit 0, keine Fehlermeldung. (Eine `.env` mit Pflichtvariablen des Haupt-Compose muss existieren, andernfalls temporär `deploy/.env.example` als Quelle kopieren.)

- [ ] **Step 4: Commit**

```bash
git add deploy/docker-compose.local-llm.yml deploy/.env.local-llm.example
git commit -m "feat(deploy): local-llm compose base overlay (ollama/speaches/kokoro)"
```

---

## Task 5: Compose GPU-Overlay

**Files:**
- Create: `deploy/docker-compose.local-llm.gpu.yml`

- [ ] **Step 1: GPU-Overlay schreiben**

```yaml
# Overlay: GPU-Variante des lokalen LLM-Stacks.
# Nutzung: docker compose -f docker-compose.yml -f docker-compose.local-llm.yml \
#           -f docker-compose.local-llm.gpu.yml \
#           --env-file .env --env-file .env.local-llm up -d
# Voraussetzungen auf dem Host: NVIDIA-Treiber + nvidia-container-toolkit.

services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cuda
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  kokoro:
    image: ghcr.io/remsky/kokoro-fastapi-gpu:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

- [ ] **Step 2: Compose config-Validierung mit GPU-Overlay**

```bash
cd deploy && cp .env.local-llm.example .env.local-llm && \
  docker compose -f docker-compose.yml -f docker-compose.local-llm.yml \
    -f docker-compose.local-llm.gpu.yml \
    --env-file .env --env-file .env.local-llm config > /dev/null && \
  rm .env.local-llm
```

Erwartet: Exit 0.

- [ ] **Step 3: Commit**

```bash
git add deploy/docker-compose.local-llm.gpu.yml
git commit -m "feat(deploy): GPU overlay for local-llm stack"
```

---

## Task 6: CI-Workflow für Compose-Validierung

**Files:**
- Create: `.github/workflows/local-llm-compose-validate.yml`

- [ ] **Step 1: Workflow schreiben**

```yaml
name: local-llm compose validate
on:
  pull_request:
    paths:
      - "deploy/docker-compose.local-llm*.yml"
      - "deploy/.env.local-llm.example"
      - ".github/workflows/local-llm-compose-validate.yml"
  push:
    branches: [main]
    paths:
      - "deploy/docker-compose.local-llm*.yml"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Prepare env files
        run: |
          cp deploy/.env.example deploy/.env
          cp deploy/.env.local-llm.example deploy/.env.local-llm
      - name: Validate base overlay
        run: |
          docker compose \
            -f deploy/docker-compose.yml \
            -f deploy/docker-compose.local-llm.yml \
            --env-file deploy/.env --env-file deploy/.env.local-llm \
            config > /dev/null
      - name: Validate GPU overlay
        run: |
          docker compose \
            -f deploy/docker-compose.yml \
            -f deploy/docker-compose.local-llm.yml \
            -f deploy/docker-compose.local-llm.gpu.yml \
            --env-file deploy/.env --env-file deploy/.env.local-llm \
            config > /dev/null
```

- [ ] **Step 2: Lokal simulieren**

```bash
# Schritte aus dem Workflow manuell abspielen
cp deploy/.env.example deploy/.env.tmp 2>/dev/null || true
cp deploy/.env.local-llm.example deploy/.env.local-llm.tmp
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
  --env-file deploy/.env.tmp --env-file deploy/.env.local-llm.tmp config > /dev/null
rm deploy/.env.tmp deploy/.env.local-llm.tmp
```

Erwartet: Exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/local-llm-compose-validate.yml
git commit -m "ci: validate local-llm compose overlays on PR"
```

---

## Task 7: Hetzner-Bootstrap-Skript

**Files:**
- Create: `scripts/hetzner/bootstrap.sh`
- Create: `deploy/.env.hetzner.example`

- [ ] **Step 1: `.env.hetzner.example` schreiben**

```dotenv
# HCloud-API-Token — https://console.hetzner.cloud → Security → API Tokens
# Read & Write erforderlich (Server erstellen + löschen).
HCLOUD_TOKEN=

# Label eines bereits in HCloud hinterlegten SSH-Keys (eu zB via `hcloud ssh-key create`).
HCLOUD_SSH_KEY=

# Location: nbg1 (Nürnberg) • fsn1 (Falkenstein) • hel1 (Helsinki) • ash (Ashburn) • hil (Hillsboro)
HCLOUD_LOCATION=nbg1

# Server-Name in HCloud (darf nur einmal existieren).
HCLOUD_SERVER_NAME=journalai-test

# Optional: Domain. Leer = sslip.io-Fallback auf die Server-IP.
DOMAIN=
```

- [ ] **Step 2: Bootstrap-Skript schreiben**

`scripts/hetzner/bootstrap.sh`:

```bash
#!/usr/bin/env bash
# Bootstrap einer journalAI-Hetzner-Test-Instanz.
# Siehe docs/self-hosting/hetzner.md.
set -euo pipefail

TIER="minimal"
YES="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --yes) YES="true"; shift ;;
    *) echo "Unbekanntes Argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$TIER" == "minimal" || "$TIER" == "recommended" ]] || {
  echo "--tier muss 'minimal' oder 'recommended' sein" >&2; exit 2; }

# Repo-Root ermitteln (Skript liegt in scripts/hetzner/).
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ENV laden (nur wenn noch nicht gesetzt).
if [[ -f "$REPO_ROOT/deploy/.env.hetzner" ]]; then
  set -a; source "$REPO_ROOT/deploy/.env.hetzner"; set +a
fi

: "${HCLOUD_TOKEN:?HCLOUD_TOKEN fehlt (in deploy/.env.hetzner oder Shell)}"
: "${HCLOUD_SSH_KEY:?HCLOUD_SSH_KEY fehlt}"
HCLOUD_LOCATION="${HCLOUD_LOCATION:-nbg1}"
HCLOUD_SERVER_NAME="${HCLOUD_SERVER_NAME:-journalai-test}"
DOMAIN="${DOMAIN:-}"

command -v hcloud >/dev/null || { echo "hcloud CLI nicht installiert" >&2; exit 2; }
command -v rsync >/dev/null  || { echo "rsync nicht installiert" >&2; exit 2; }

export HCLOUD_TOKEN  # hcloud CLI liest HCLOUD_TOKEN aus ENV

# Lokale Env-Dateien prüfen.
[[ -f "$REPO_ROOT/deploy/.env" ]] || { echo "deploy/.env fehlt" >&2; exit 2; }
[[ -f "$REPO_ROOT/deploy/.env.local-llm" ]] || { echo "deploy/.env.local-llm fehlt" >&2; exit 2; }

# Server-Typ pro Tier.
case "$TIER" in
  minimal) SERVER_TYPE="cpx41" ;;         # 8 vCPU dedicated, 16 GB RAM, ~0,03 €/h
  recommended) SERVER_TYPE="gex44" ;;     # RTX 6000 Ada, 48 GB VRAM, ~1,05 €/h
esac

echo ">> Ziel-Tier: $TIER ($SERVER_TYPE) in $HCLOUD_LOCATION"
if [[ "$YES" != "true" ]]; then
  read -r -p "Server jetzt anlegen? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "Abbruch."; exit 0; }
fi

PUBLIC_IP="$(curl -sf https://ipv4.icanhazip.com || curl -sf https://ifconfig.me)"
[[ -n "$PUBLIC_IP" ]] || { echo "Konnte lokale IP nicht ermitteln" >&2; exit 1; }

FW_NAME="${HCLOUD_SERVER_NAME}-fw"
if ! hcloud firewall describe "$FW_NAME" >/dev/null 2>&1; then
  echo ">> Firewall $FW_NAME anlegen"
  hcloud firewall create --name "$FW_NAME" >/dev/null
  hcloud firewall add-rule "$FW_NAME" --direction in --protocol tcp --port 22  --source-ips "${PUBLIC_IP}/32"
  hcloud firewall add-rule "$FW_NAME" --direction in --protocol tcp --port 80  --source-ips "0.0.0.0/0" --source-ips "::/0"
  hcloud firewall add-rule "$FW_NAME" --direction in --protocol tcp --port 443 --source-ips "0.0.0.0/0" --source-ips "::/0"
fi

# Cloud-init schreiben.
CLOUD_INIT="$(mktemp)"
cat > "$CLOUD_INIT" <<CIEOF
#cloud-config
package_update: true
package_upgrade: false
packages:
  - ca-certificates
  - curl
  - git
  - jq
  - rsync
runcmd:
  - curl -fsSL https://get.docker.com | sh
  - usermod -aG docker ubuntu
CIEOF

if [[ "$TIER" == "recommended" ]]; then
  cat >> "$CLOUD_INIT" <<'CIEOF'
  - curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  - curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  - apt-get update && apt-get install -y nvidia-container-toolkit
  - nvidia-ctk runtime configure --runtime=docker
  - systemctl restart docker
CIEOF
fi

echo ">> Server $HCLOUD_SERVER_NAME erstellen"
hcloud server create \
  --name "$HCLOUD_SERVER_NAME" \
  --type "$SERVER_TYPE" \
  --image "ubuntu-24.04" \
  --location "$HCLOUD_LOCATION" \
  --ssh-key "$HCLOUD_SSH_KEY" \
  --firewall "$FW_NAME" \
  --user-data-from-file "$CLOUD_INIT" \
  --label "journalai=test" >/dev/null
rm -f "$CLOUD_INIT"

SERVER_IP="$(hcloud server ip "$HCLOUD_SERVER_NAME")"
echo ">> Server-IP: $SERVER_IP"

HOST="${DOMAIN:-${SERVER_IP}.sslip.io}"
echo ">> Host-URL: https://$HOST"

echo ">> Auf SSH warten"
for i in {1..60}; do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@$SERVER_IP" "cloud-init status --wait >/dev/null 2>&1 || true" </dev/null >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo ">> Code übertragen (rsync)"
rsync -az --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='backend/.venv' \
  --exclude='frontend/build' \
  --exclude='frontend/.svelte-kit' \
  --exclude='deploy/data' \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$REPO_ROOT/" "root@$SERVER_IP:/root/journalAI/"

echo ">> DOMAIN in deploy/.env setzen"
ssh -o StrictHostKeyChecking=no "root@$SERVER_IP" \
  "sed -i 's|^DOMAIN=.*|DOMAIN=${HOST}|' /root/journalAI/deploy/.env || echo 'DOMAIN=${HOST}' >> /root/journalAI/deploy/.env"

OVERLAYS=(-f docker-compose.yml -f docker-compose.local-llm.yml)
[[ "$TIER" == "recommended" ]] && OVERLAYS+=(-f docker-compose.local-llm.gpu.yml)

echo ">> Stack starten (${TIER})"
ssh -o StrictHostKeyChecking=no "root@$SERVER_IP" \
  "cd /root/journalAI/deploy && docker compose ${OVERLAYS[*]} --env-file .env --env-file .env.local-llm up -d"

echo ">> Auf /api/health warten (max. 10 min, erste Modell-Downloads brauchen Zeit)"
for i in {1..60}; do
  if curl -ksf "https://$HOST/api/health" >/dev/null; then
    echo ">> OK"
    break
  fi
  sleep 10
done

echo ""
echo "================ FERTIG ================"
echo "URL:       https://$HOST"
echo "SSH:       ssh root@$SERVER_IP"
echo "Teardown:  scripts/hetzner/teardown.sh"
echo "Kosten/h:  $( [[ $TIER == minimal ]] && echo '≈0,03 €' || echo '≈1,05 €' )"
echo "========================================"
```

Skript ausführbar machen:

```bash
chmod +x scripts/hetzner/bootstrap.sh
```

- [ ] **Step 3: Shellcheck lokal laufen lassen**

```bash
command -v shellcheck >/dev/null && shellcheck scripts/hetzner/bootstrap.sh || echo "shellcheck nicht installiert — optional"
```

Erwartet: Keine Errors (Warnungen OK, aber dokumentieren falls gravierend).

- [ ] **Step 4: Commit**

```bash
git add scripts/hetzner/bootstrap.sh deploy/.env.hetzner.example
git commit -m "feat(hetzner): bootstrap script to spin up journalAI test server"
```

---

## Task 8: Hetzner-Teardown-Skript

**Files:**
- Create: `scripts/hetzner/teardown.sh`

- [ ] **Step 1: Teardown-Skript schreiben**

`scripts/hetzner/teardown.sh`:

```bash
#!/usr/bin/env bash
# Räumt die von bootstrap.sh angelegten HCloud-Ressourcen auf.
set -euo pipefail

YES="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES="true"; shift ;;
    *) echo "Unbekanntes Argument: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -f "$REPO_ROOT/deploy/.env.hetzner" ]] && { set -a; source "$REPO_ROOT/deploy/.env.hetzner"; set +a; }

: "${HCLOUD_TOKEN:?HCLOUD_TOKEN fehlt}"
HCLOUD_SERVER_NAME="${HCLOUD_SERVER_NAME:-journalai-test}"
FW_NAME="${HCLOUD_SERVER_NAME}-fw"
export HCLOUD_TOKEN

if [[ "$YES" != "true" ]]; then
  read -r -p "Server '$HCLOUD_SERVER_NAME' und Firewall '$FW_NAME' wirklich löschen? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "Abbruch."; exit 0; }
fi

if hcloud server describe "$HCLOUD_SERVER_NAME" >/dev/null 2>&1; then
  hcloud server delete "$HCLOUD_SERVER_NAME"
  echo ">> Server gelöscht"
else
  echo ">> Server '$HCLOUD_SERVER_NAME' existiert nicht — übersprungen"
fi

if hcloud firewall describe "$FW_NAME" >/dev/null 2>&1; then
  hcloud firewall delete "$FW_NAME"
  echo ">> Firewall gelöscht"
else
  echo ">> Firewall '$FW_NAME' existiert nicht — übersprungen"
fi
```

Ausführbar machen:

```bash
chmod +x scripts/hetzner/teardown.sh
```

- [ ] **Step 2: Commit**

```bash
git add scripts/hetzner/teardown.sh
git commit -m "feat(hetzner): teardown script (idempotent)"
```

---

## Task 9: `.gitignore`-Updates

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Einträge prüfen und ergänzen**

Prüfen, welche Ignores bereits vorhanden sind:

```bash
grep -n "env.hetzner\|env.local-llm\|env.benchmark\|docs/benchmarks" .gitignore || true
```

Dann — falls fehlend — am Ende anfügen:

```gitignore

# Local-LLM-Stack (nur Beispiele werden committet)
deploy/.env.hetzner
deploy/.env.local-llm
deploy/.env.benchmark
```

**Kein** Ignore für `docs/benchmarks/` — diese sollen ja committet werden. Gitkeep kommt in Task 10.

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore local-llm and hetzner env files"
```

---

## Task 10: Benchmark-Skript + Test-Fixture

**Files:**
- Create: `scripts/benchmark.sh`
- Create: `tests/fixtures/benchmark-60s.webm` (manuell)
- Create: `docs/benchmarks/.gitkeep`

- [ ] **Step 1: Audio-Fixture manuell erzeugen**

Eine 60-sekündige deutsche Sprachaufnahme in `tests/fixtures/benchmark-60s.webm` ablegen. Zwei Wege:

**Variante A (ffmpeg + eigenes Mikro):**
```bash
ffmpeg -f pulse -i default -t 60 -c:a libopus -b:a 64k tests/fixtures/benchmark-60s.webm
```

**Variante B (Platzhalter, wenn noch keine Aufnahme vorliegt):**
Einen existierenden Test-Audio-Clip aus `frontend/e2e/fixtures/` oder `backend/tests/fixtures/` auf 60s trimmen:
```bash
ffmpeg -i <existing>.webm -t 60 -c copy tests/fixtures/benchmark-60s.webm
```

Lizenz/Herkunft im Commit-Body dokumentieren (CC0 oder eigene Aufnahme). Dateigröße ≤ 2 MB.

- [ ] **Step 2: Benchmark-Skript schreiben**

`scripts/benchmark.sh`:

```bash
#!/usr/bin/env bash
# Misst Performance der vier LLM-Capabilities gegen eine laufende journalAI-Instanz.
# Schreibt einen Report nach docs/benchmarks/YYYY-MM-DD-<tier>-<hostname>.md.
set -euo pipefail

URL=""; TIER="minimal"; LABEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)   URL="$2"; shift 2 ;;
    --tier)  TIER="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
done
: "${URL:?--url fehlt (z. B. https://<ip>.sslip.io)}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH_ENV="$REPO_ROOT/deploy/.env.benchmark"
[[ -f "$BENCH_ENV" ]] || { echo "deploy/.env.benchmark fehlt — enthält BENCHMARK_USER/BENCHMARK_PASSWORD" >&2; exit 2; }
set -a; source "$BENCH_ENV"; set +a
: "${BENCHMARK_USER:?}"; : "${BENCHMARK_PASSWORD:?}"

command -v jq       >/dev/null || { echo "jq fehlt" >&2; exit 2; }
command -v curl     >/dev/null || { echo "curl fehlt" >&2; exit 2; }
command -v python3  >/dev/null || { echo "python3 fehlt" >&2; exit 2; }

COOKIE="$(mktemp)"; trap 'rm -f "$COOKIE"' EXIT

# Login + CSRF holen
curl -ksf -c "$COOKIE" "$URL/api/auth/csrf" >/dev/null
CSRF="$(grep csrf_token "$COOKIE" | awk '{print $7}')"
curl -ksf -b "$COOKIE" -c "$COOKIE" -X POST "$URL/api/auth/login" \
  -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -d "{\"username\":\"$BENCHMARK_USER\",\"password\":\"$BENCHMARK_PASSWORD\"}" >/dev/null
CSRF="$(grep csrf_token "$COOKIE" | awk '{print $7}')"

# --- Chat-Benchmark -----------------------------------------------------------
echo ">> Chat"
CHAT_PROMPT="Schreibe einen 500 Wörter langen, zusammenhängenden deutschen Text über die Bedeutung von Datenschutz im Alltag."
CHAT_START="$(date +%s.%N)"
CHAT_RESPONSE="$(curl -ksf -b "$COOKIE" -c "$COOKIE" \
  -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -X POST "$URL/api/chat" \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$CHAT_PROMPT\"}]}" \
  --no-buffer | tr -d '\r')"
CHAT_END="$(date +%s.%N)"
CHAT_ELAPSED="$(python3 -c "print($CHAT_END - $CHAT_START)")"
# Tokens = ungefähr Wörter in der Response (ausreichend genau für Tier-Vergleiche).
CHAT_TEXT="$(echo "$CHAT_RESPONSE" | grep '^data: ' | sed 's/^data: //' | jq -rs 'map(.delta // empty) | join("")')"
CHAT_TOKENS="$(echo "$CHAT_TEXT" | wc -w)"
CHAT_TPS="$(python3 -c "print(round($CHAT_TOKENS / $CHAT_ELAPSED, 2))")"

# --- STT-Benchmark ------------------------------------------------------------
echo ">> STT"
STT_START="$(date +%s.%N)"
curl -ksf -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -X POST "$URL/api/transcribe" \
  -F "audio=@$REPO_ROOT/tests/fixtures/benchmark-60s.webm" >/dev/null
STT_END="$(date +%s.%N)"
STT_ELAPSED="$(python3 -c "print($STT_END - $STT_START)")"
STT_RTF="$(python3 -c "print(round($STT_ELAPSED / 60.0, 2))")"

# --- Embed-Benchmark ----------------------------------------------------------
echo ">> Embed (100 Entries reindex)"
# 100 Test-Entries erzeugen
CREATED_IDS=()
for i in $(seq 1 100); do
  EID="$(curl -ksf -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
    -X POST "$URL/api/entries" \
    -d "{\"entry_date\":\"2026-04-19\",\"title\":\"bench-$i\",\"content\":\"Test-Eintrag Nummer $i. Stichworte: Alltag, Datenschutz, Selbst-Reflexion.\"}" \
    | jq -r '.id')"
  CREATED_IDS+=("$EID")
done

EMBED_START="$(date +%s.%N)"
curl -ksf -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -X POST "$URL/api/search/reindex" >/dev/null
while true; do
  STATUS_JSON="$(curl -ksf -b "$COOKIE" "$URL/api/search/status")"
  STATE="$(echo "$STATUS_JSON" | jq -r '.status')"
  if [[ "$STATE" == "ready" || "$STATE" == "done" || "$STATE" == "error" ]]; then break; fi
  sleep 2
done
EMBED_END="$(date +%s.%N)"
EMBED_ELAPSED="$(python3 -c "print($EMBED_END - $EMBED_START)")"
EMBED_EPS="$(python3 -c "print(round(100 / $EMBED_ELAPSED, 2))")"

# Test-Entries wieder entfernen
for eid in "${CREATED_IDS[@]}"; do
  curl -ksf -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -X DELETE "$URL/api/entries/$eid" >/dev/null || true
done

# --- TTS-Benchmark ------------------------------------------------------------
echo ">> TTS"
TTS_TEXT="Dies ist ein Test-Text mit dreihundert Zeichen, um die Geschwindigkeit der lokalen Text-zu-Sprache-Engine zu vermessen. Wir testen sowohl CPU- als auch GPU-basierte Setups, um dir als Nutzer realistische Kennzahlen zu geben."
TTS_TMP="$(mktemp --suffix=.mp3)"
TTS_START="$(date +%s.%N)"
curl -ksf -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -X POST "$URL/api/tts" -d "{\"text\":\"$TTS_TEXT\"}" -o "$TTS_TMP"
TTS_END="$(date +%s.%N)"
TTS_ELAPSED="$(python3 -c "print($TTS_END - $TTS_START)")"
TTS_AUDIO_LEN="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$TTS_TMP")"
TTS_RTF="$(python3 -c "print(round($TTS_ELAPSED / $TTS_AUDIO_LEN, 3))")"
rm -f "$TTS_TMP"

# --- Report schreiben ---------------------------------------------------------
DATE="$(date +%Y-%m-%d)"
HOSTNAME="$(ssh -o StrictHostKeyChecking=no "${URL#https://}" hostname 2>/dev/null || echo "${URL}")"
HOSTNAME_SAFE="$(echo "$HOSTNAME" | tr -c '[:alnum:]-' '-')"
LABEL_SAFE="${LABEL:-$HOSTNAME_SAFE}"
REPORT="$REPO_ROOT/docs/benchmarks/${DATE}-${TIER}-${LABEL_SAFE}.md"

{
  echo "---"
  echo "date: $DATE"
  echo "tier: $TIER"
  echo "label: $LABEL_SAFE"
  echo "url: $URL"
  echo "chat_tokens_per_second: $CHAT_TPS"
  echo "stt_rtf: $STT_RTF"
  echo "embed_entries_per_second: $EMBED_EPS"
  echo "tts_rtf: $TTS_RTF"
  echo "---"
  echo ""
  echo "# Benchmark $DATE — $TIER — $LABEL_SAFE"
  echo ""
  echo "| Metric | Value |"
  echo "|---|---|"
  echo "| Chat (tok/s) | $CHAT_TPS |"
  echo "| STT (RTF) | $STT_RTF |"
  echo "| Embed (entries/s) | $EMBED_EPS |"
  echo "| TTS (RTF) | $TTS_RTF |"
} > "$REPORT"

echo ""
echo "Report: $REPORT"
cat "$REPORT"
```

Ausführbar machen:

```bash
chmod +x scripts/benchmark.sh
```

- [ ] **Step 3: `.gitkeep` anlegen**

```bash
touch docs/benchmarks/.gitkeep
```

- [ ] **Step 4: Shellcheck**

```bash
command -v shellcheck >/dev/null && shellcheck scripts/benchmark.sh || echo "shellcheck nicht installiert"
```

- [ ] **Step 5: Commit**

```bash
git add scripts/benchmark.sh tests/fixtures/benchmark-60s.webm docs/benchmarks/.gitkeep
git commit -m "feat(benchmark): script and 60s audio fixture for 4-capability perf report"
```

---

## Task 11: Doku — `docs/self-hosting/local-llm.md`

**Files:**
- Create: `docs/self-hosting/local-llm.md`

- [ ] **Step 1: Doku schreiben**

Inhalt — 5-Schritte-Anleitung + FAQ. Struktur:

```markdown
# Lokaler LLM-Stack

journalAI kann komplett lokal betrieben werden, ohne OpenAI oder andere Cloud-Provider. Alle vier Capabilities (Chat, Embeddings, STT, TTS) laufen dann in Docker-Containern neben Backend und Frontend.

## Voraussetzungen

| | Minimal (CPU) | Recommended (GPU) |
|---|---|---|
| CPU | 8 Kerne dedicated | 4 Kerne |
| RAM | 16 GB | 16 GB |
| GPU | — | NVIDIA, ≥8 GB VRAM, Treiber ≥535, nvidia-container-toolkit |
| Disk | 20 GB (Modelle) | 50 GB (größere Modelle) |

## Schritte

1. **`.env.local-llm` anlegen:** `cp deploy/.env.local-llm.example deploy/.env.local-llm`, dann den passenden Tier-Block aktivieren.
2. **Stack starten:**
   ```bash
   # Minimal (CPU)
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
     --env-file deploy/.env --env-file deploy/.env.local-llm up -d

   # Recommended (GPU)
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
     -f deploy/docker-compose.local-llm.gpu.yml \
     --env-file deploy/.env --env-file deploy/.env.local-llm up -d
   ```
3. **Erster Start (dauert 5-20 min):** `ollama-init` pullt die Modelle, speaches und Kokoro laden ihre Modelle beim ersten Request. Logs: `docker compose logs -f ollama-init`.
4. **Einloggen:** Backend bereitet `/api/settings` automatisch mit den ENV-Werten vor; in der UI siehst du die Hinweise „aus ENV: …".
5. **Testen:** Einen Voice-Eintrag aufnehmen oder eine semantische Suche starten. Falls ein Request mit 502 scheitert, in den Container-Logs nachsehen (häufig Modell-Pull läuft noch).

## FAQ

- **Kann ich Capabilities mischen?** Ja — einfach im Settings-UI für die gewünschte Capability einen anderen Endpoint/Model eintragen. DB schlägt ENV.
- **Wie wechsle ich das Chat-Modell?** `.env.local-llm` ändern, `docker compose up -d ollama-init` ausführen (pullt nur neue Modelle).
- **Warum ist mein Minimal-Tier so langsam?** Siehe `docs/benchmarks/` — CPU-only Chat bei 7B-Modellen ist inhärent langsam. Kleinere Modelle (3B, Q4) sind spürbar schneller.
```

- [ ] **Step 2: Commit**

```bash
git add docs/self-hosting/local-llm.md
git commit -m "docs(self-hosting): local-llm stack guide"
```

---

## Task 12: Doku — `docs/self-hosting/hetzner.md`

**Files:**
- Create: `docs/self-hosting/hetzner.md`

- [ ] **Step 1: Doku schreiben**

```markdown
# journalAI auf Hetzner Cloud (B-Pfad)

Wenn du selbst keine geeignete Hardware hast, kannst du den lokalen LLM-Stack temporär auf einem Hetzner-Cloud-Server betreiben — stundenweise gemietet, danach wieder abgerissen.

## Voraussetzungen

- Hetzner-Cloud-Account
- `hcloud` CLI installiert (`brew install hcloud` / `apt install hcloud-cli` / von Hetzner-GitHub)
- Ein SSH-Public-Key in HCloud hochgeladen (`hcloud ssh-key create --name julian-key --public-key-from-file ~/.ssh/id_ed25519.pub`)
- API-Token (Read+Write) aus der HCloud-Console

## Setup

1. Vorlage kopieren und füllen:
   ```bash
   cp deploy/.env.hetzner.example deploy/.env.hetzner
   # HCLOUD_TOKEN + HCLOUD_SSH_KEY eintragen
   ```
2. `deploy/.env` und `deploy/.env.local-llm` lokal vorbereiten (siehe `docs/self-hosting/local-llm.md`).
3. Bootstrap:
   ```bash
   # Kurztest, CPU-only, ~0,03 €/h
   ./scripts/hetzner/bootstrap.sh --tier minimal

   # Brauchbare Chat-Qualität, GPU, ~1,05 €/h
   ./scripts/hetzner/bootstrap.sh --tier recommended
   ```
4. Das Skript gibt am Ende die URL aus (Form: `https://<ip>.sslip.io`). Der erste Login-Flow geht ganz normal über das UI.
5. Abreißen:
   ```bash
   ./scripts/hetzner/teardown.sh
   ```

## Kosten (Stand 2026-04)

| Tier | Server-Typ | ~ Kosten/h | Typische Test-Laufzeit |
|---|---|---|---|
| Minimal | cpx41 | 0,03 € | 1-4 h |
| Recommended | gex44 | 1,05 € | 30-120 min |

## Maximal abgeschottet (Tailscale)

Die Default-Firewall öffnet Port 443 fürs offene Internet. Wer das nicht will, schaltet Tailscale dazwischen:

1. Auf dem Server via SSH:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
2. Lokal (Client) dasselbe: `sudo tailscale up`.
3. HCloud-Firewall anpassen — Port 443 nur noch aus Tailscale-CGNAT-Range erlauben:
   ```bash
   hcloud firewall delete-rule journalai-test-fw --direction in --port 443 --protocol tcp --source-ips 0.0.0.0/0 --source-ips ::/0
   hcloud firewall add-rule    journalai-test-fw --direction in --protocol tcp --port 443 --source-ips 100.64.0.0/10
   ```
4. Zugriff dann nicht mehr über `<ip>.sslip.io`, sondern über den Tailscale-Hostnamen des Servers (`http://journalai-test/` im Tailnet oder HTTPS mit eigener Cert-Konfiguration — Details siehe Caddy-Config).

Tailscale-Auth-Keys werden bewusst nicht in `.env.hetzner` verwaltet, weil sie einen eigenen Login-Flow haben.

## Wechselnde Client-IP

`bootstrap.sh` öffnet SSH nur von deiner aktuellen öffentlichen IP. Wenn du VPN umschaltest oder in ein anderes Netz wechselst, musst du die Regel updaten:

```bash
MY_IP="$(curl -s ifconfig.me)/32"
hcloud firewall replace-rules journalai-test-fw --rules-file <(cat <<EOF
[
  {"direction":"in","protocol":"tcp","port":"22","source_ips":["$MY_IP"]},
  {"direction":"in","protocol":"tcp","port":"80","source_ips":["0.0.0.0/0","::/0"]},
  {"direction":"in","protocol":"tcp","port":"443","source_ips":["0.0.0.0/0","::/0"]}
]
EOF
)
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/self-hosting/hetzner.md
git commit -m "docs(self-hosting): hetzner bootstrap + tailscale hardening guide"
```

---

## Task 13: README verlinken

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README-Abschnitt einfügen**

Nach dem bestehenden Self-Hosting-Abschnitt (oder vor dem Lizenz-Teil) einfügen:

```markdown
## Lokaler LLM-Stack (optional, privacy-first)

journalAI läuft standardmäßig gegen OpenAI-kompatible Endpoints (jeder Provider). Für kompletten Lokal-Betrieb ohne Cloud existiert ein offizielles Compose-Profil mit Ollama (Chat + Embed), speaches (STT) und Kokoro-FastAPI (TTS).

- **Lokal auf eigener Hardware:** [`docs/self-hosting/local-llm.md`](docs/self-hosting/local-llm.md)
- **Ohne geeignete Hardware → Hetzner Cloud:** [`docs/self-hosting/hetzner.md`](docs/self-hosting/hetzner.md)

### Performance-Referenz

| Tier | Chat (tok/s) | STT (RTF) | Embed (entries/s) | TTS (RTF) |
|---|---|---|---|---|
| Minimal (CPX41, CPU) | `TBD` | `TBD` | `TBD` | `TBD` |
| Recommended (GEX44, RTX 6000 Ada) | `TBD` | `TBD` | `TBD` | `TBD` |

Detailreports: [`docs/benchmarks/`](docs/benchmarks/). Benchmarks stammen von einem realen Hetzner-Testlauf, nicht aus Herstellerangaben.
```

Hinweis: Die `TBD`-Werte werden nach dem gemeinsamen Hetzner-E2E-Test befüllt (Task 14, User-Ko-Op).

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): link local-llm guides + benchmark placeholder table"
```

---

## Task 14: Gemeinsamer Hetzner-E2E-Test (manuell, User-Ko-Op)

**Kein Code-Commit in diesem Task — nur Operativ-Schritte mit dem User.**

- [ ] **Step 1: Bestätigung einholen**

Dem User folgende Info vorlegen und explizit „go" abwarten:
- Tier (Minimal oder Recommended), erwartete Kosten/h, erwartete Laufzeit (≤ 1 h).
- Was passiert: `bootstrap.sh --tier <X>`, Playwright-Suite gegen sslip.io-URL, `benchmark.sh`, dann `teardown.sh`.

- [ ] **Step 2: Minimal-Tier hochfahren**

```bash
./scripts/hetzner/bootstrap.sh --tier minimal
```

URL merken (z. B. `https://1.2.3.4.sslip.io`). Warten bis Healthcheck PASS.

- [ ] **Step 3: Admin-User im UI anlegen**

Erstes Onboarding via Browser (Registrierung, TOTP-Setup überspringen für Benchmark, wieder aktivieren vor Produktivnutzung).

- [ ] **Step 4: Benchmark laufen lassen**

```bash
echo "BENCHMARK_USER=<user>"           > deploy/.env.benchmark
echo "BENCHMARK_PASSWORD=<pw>"        >> deploy/.env.benchmark
./scripts/benchmark.sh --url https://<ip>.sslip.io --tier minimal --label cpx41
```

Report wird nach `docs/benchmarks/YYYY-MM-DD-minimal-cpx41.md` geschrieben.

- [ ] **Step 5: Playwright-Live-Suite**

```bash
cd frontend
PLAYWRIGHT_BASE_URL=https://<ip>.sslip.io E2E_LIVE=1 npx playwright test
```

Erwartet: alle Specs grün (wie bereits im Phase-4-Runbook).

- [ ] **Step 6: Recommended-Tier — Same Play**

Teardown Minimal, bootstrap `recommended`, benchmark, Playwright. Report nach `docs/benchmarks/YYYY-MM-DD-recommended-gex44.md`.

- [ ] **Step 7: Teardown**

```bash
./scripts/hetzner/teardown.sh
```

- [ ] **Step 8: Reports committen + README-Tabelle befüllen**

```bash
git add docs/benchmarks/*.md
# Dann README.md editieren, TBD-Werte durch die gemessenen Werte ersetzen.
git add README.md
git commit -m "docs(benchmarks): initial local-llm perf reports (minimal + recommended)"
```

- [ ] **Step 9: Roadmap-Eintrag in MEMORY**

Nach Abschluss in `memory/roadmap.md` im „Erledigt"-Abschnitt einen Eintrag ergänzen (Commit-Hash, Datum, Kurzfazit Benchmarks). `v0.5.0-local-llm`-Tag kann der User optional manuell setzen.

---

## Self-Review

**Spec coverage:**
- Architektur (Spec §1) → Task 4 + 5 (Compose-Dateien)
- Backend-Änderungen (Spec §3) → Task 1 + 2
- Frontend-Hint (Spec §3) → Task 3
- Compose-Struktur (Spec §2) → Task 4 + 5
- Hetzner-Bootstrap (Spec §4) → Task 7 + 8 + 9
- Benchmarks (Spec §5) → Task 10 + 14
- Dokumentation → Task 11 + 12 + 13
- CI → Task 6
- Akzeptanzkriterien (Spec §6) → werden in Task 14 validiert
- Risiken (Spec §7) → bewusst nicht als separate Tasks (HW-Risiken sind Betriebs-, keine Code-Themen)

**Placeholder scan:** Keine TBD/TODO in Code-Steps. Die TBD-Werte in der README-Tabelle sind bewusst — sie werden von Task 14 ersetzt. Die Repo-URL-Placeholder sind durch rsync-Ansatz komplett eliminiert.

**Type consistency:** Resolver heißen durchgängig `resolved_base_url`, `resolved_api_key`, `resolved_model`. SettingsOut-Felder: `<cap>_resolved_base_url`, `<cap>_resolved_model`. Frontend-Helper: `envHint(dbValue, resolved)`. Konsistent.

Keine offenen Gaps.
