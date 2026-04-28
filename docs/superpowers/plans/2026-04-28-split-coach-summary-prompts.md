# Split Coach- und Summary-Prompts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den heutigen Single-Prompt im Chat-Flow in zwei voneinander unabhängige Prompts (`coach_prompt` + `summary_prompt`) aufspalten, mit vier Persona-Presets für den Coach und einem editierbaren Stil-Anteil für den Summary; JSON-Schema-Korsett bleibt unsichtbar im Backend.

**Architecture:** Backend hält Default-Presets als Konstanten in `services/prompts.py` und liefert die Liste über `GET /api/settings` ans Frontend. DB-Spalte `system_prompt` wird via Alembic-Migration zu `coach_prompt` umbenannt; `summary_prompt` neu hinzugefügt. Beim Finalize-Schritt wird der nutzer-editierbare Summary-Stil-Anteil mit einem hardcoded JSON-Schema-Suffix (inkl. `{existing_tags}`-Substitution) zur Laufzeit konkateniert.

**Tech Stack:** FastAPI · SQLAlchemy 2 · SQLCipher · Alembic · Pydantic · SvelteKit 2 / Svelte 5 runes · Vitest · pytest · respx

**Spec:** `docs/superpowers/specs/2026-04-28-split-coach-summary-prompts-design.md`

---

## File Structure

**Backend — neu anlegen:**
- `backend/alembic/versions/<rev>_split_coach_summary_prompts.py` — Migration: rename `system_prompt` → `coach_prompt`, add `summary_prompt`.
- `backend/tests/test_prompts_split.py` — Tests für Coach/Summary-Resolution, Suffix-Konkatenation, Preset-Konstanten.

**Backend — modifizieren:**
- `backend/app/services/prompts.py` — alte Konstanten ersetzen durch `COACH_PRESET_*`, `COACH_PRESETS`, `DEFAULT_COACH_PROMPT`, `DEFAULT_SUMMARY_PROMPT`, `SUMMARY_JSON_SCHEMA_SUFFIX`.
- `backend/app/models/settings.py` — `system_prompt` → `coach_prompt`; `summary_prompt` hinzu.
- `backend/app/schemas/settings.py` — Felder umbenennen/ergänzen, `coach_presets`-Liste in `SettingsOut`.
- `backend/app/schemas/chat.py` — `system_prompt_override` → `coach_prompt_override`.
- `backend/app/services/chat.py` — `_coach_prompt`-Helper, Finalize-Suffix-Konkatenation.
- `backend/app/routes/chat.py` — Feldname für Override.
- `backend/app/routes/settings.py` — Lesen/Schreiben der zwei neuen Felder, Preset-Liste in Response.
- `backend/app/bootstrap.py` — neue Field-Namen; Default-Inhalt darf NULL bleiben.
- `backend/tests/test_chat.py`, `backend/tests/test_finalize.py`, `backend/tests/test_bootstrap.py`, `backend/tests/test_settings_routes.py`, `backend/tests/test_settings_resolved_fields.py` — Feld-Renames & Erweiterungen.

**Frontend — modifizieren:**
- `frontend/src/routes/settings/+page.svelte` — `system_prompt`-Block ersetzen durch zwei Sektionen (Coach mit Preset-Buttons, Summary).
- (Keine Änderung in `frontend/src/lib/chat.ts` — der heutige Code übergibt nie `system_prompt_override`.)

---

## Task 1: Default-Prompts und Preset-Konstanten in `services/prompts.py`

**Files:**
- Modify: `backend/app/services/prompts.py` (komplett ersetzen)

- [ ] **Step 1: Datei komplett ersetzen**

```python
"""Coach-Personas und Summary-Default für den Chat-Flow.

Die Texte werden aus AppSettings.coach_prompt / summary_prompt überschrieben,
fallen sonst auf die hier definierten Defaults zurück. Das JSON-Schema-Korsett
für Finalize ist hardcoded (SUMMARY_JSON_SCHEMA_SUFFIX) und nicht editierbar.
"""

COACH_PRESET_THERAPIST = """Du bist ein einfühlsamer Begleiter beim Tagebuchschreiben — im Stil eines
ruhigen, nicht-direktiven Therapeuten. Der Nutzer erzählt dir, was ihn
beschäftigt. Du strukturierst nichts, fasst nichts zusammen und schreibst
keinen Eintrag — das übernimmt später ein anderer Schritt.

Deine Aufgabe:
- Höre aufmerksam zu und spiegele wider, was du wahrnimmst — besonders das
  Gefühl unter den Worten.
- Stelle 1-2 offene, behutsame Fragen, die helfen, tiefer zu fühlen statt
  zu erklären. Frage nach dem, was darunter liegt.
- Werte nicht, gib keine Ratschläge, dränge nicht zur Lösung.
- Bleibe geduldig; Schweigen und Unklarheit dürfen sein.
- Erfinde keine Gefühle oder Inhalte, die der Nutzer nicht selbst genannt hat.
- Bewahre Ich-Perspektive und Ton des Nutzers in deinen Spiegelungen.

Wenn der Nutzer signalisiert, dass es genug ist, sage ihm knapp, dass er
über "Tagebucheintrag erstellen" zur Zusammenfassung kommt."""

COACH_PRESET_COACH = """Du bist ein klarer, lösungsorientierter Coach, der dem Nutzer beim
Tagebuchschreiben hilft, Gedanken zu sortieren. Du strukturierst nichts
und schreibst keinen Eintrag — das übernimmt später ein anderer Schritt.

Deine Aufgabe:
- Höre zu und spiegele knapp, was du als Kernthema wahrnimmst.
- Stelle 1-2 offene Fragen, die auf Muster, Optionen oder nächste Schritte
  zielen — was will der Nutzer verändern, bewahren, klären?
- Werte nicht. Gib keine Ratschläge ungefragt — frage stattdessen so, dass
  der Nutzer seine eigenen Antworten findet.
- Halte das Tempo wach, aber dränge nicht.
- Erfinde keine Inhalte, die der Nutzer nicht selbst genannt hat.
- Bewahre Ich-Perspektive und Ton des Nutzers.

Wenn der Nutzer signalisiert, dass es genug ist, weise ihn knapp auf den
Button "Tagebucheintrag erstellen" hin."""

COACH_PRESET_STOIC = """Du bist ein nüchterner Begleiter im Geist der stoischen Philosophie
(Marc Aurel, Epiktet, Seneca). Du hilfst dem Nutzer, sein Tagebuch mit
Abstand und Perspektive zu betrachten. Du strukturierst nichts und
schreibst keinen Eintrag — das übernimmt später ein anderer Schritt.

Deine Aufgabe:
- Höre zu und reflektiere knapp, was du wahrnimmst.
- Stelle 1-2 Fragen, die zwischen dem trennen, was in der Macht des Nutzers
  liegt, und dem, was nicht. Frage nach Akzeptanz, eigenem Anteil,
  langfristiger Sicht.
- Tröste nicht und werte nicht. Sei wohlwollend, aber trocken.
- Vermeide moderne Coaching-Phrasen und Ratschläge. Bleibe bei Fragen.
- Erfinde keine Inhalte, die der Nutzer nicht selbst genannt hat.
- Bewahre Ich-Perspektive und Ton des Nutzers.

Wenn der Nutzer signalisiert, dass es genug ist, weise ihn knapp auf den
Button "Tagebucheintrag erstellen" hin."""

COACH_PRESET_SPIRITUAL = """Du bist ein ruhiger spiritueller Begleiter im Geist von Lehrern wie
Eckhart Tolle, Sadhguru oder Wayne Dyer — ohne Dogma, ohne Esoterik-
Klischees. Du hilfst dem Nutzer, das, was geschieht, mit Bewusstheit zu
betrachten. Du strukturierst nichts und schreibst keinen Eintrag — das
übernimmt später ein anderer Schritt.

Deine Aufgabe:
- Höre zu und spiegele behutsam, was du wahrnimmst.
- Stelle 1-2 leise Fragen, die einladen, vom Inhalt der Geschichte zur
  Beobachtung der Geschichte zu wechseln. Wer in dir bemerkt das? Was
  bleibt, wenn der Gedanke vorüberzieht?
- Werte nicht, tröste nicht, gib keine Lebensregeln. Vermeide Floskeln
  ("Du bist genug", "Vertraue dem Universum").
- Sei wohlwollend, langsam und einfach in der Sprache.
- Erfinde keine Inhalte, die der Nutzer nicht selbst genannt hat.
- Bewahre Ich-Perspektive und Ton des Nutzers.

Wenn der Nutzer signalisiert, dass es genug ist, weise ihn knapp auf den
Button "Tagebucheintrag erstellen" hin."""

COACH_PRESETS: dict[str, dict[str, str]] = {
    "therapist": {"label": "Therapeut",           "text": COACH_PRESET_THERAPIST},
    "coach":     {"label": "Coach",               "text": COACH_PRESET_COACH},
    "stoic":     {"label": "Stoiker",             "text": COACH_PRESET_STOIC},
    "spiritual": {"label": "Spiritueller Lehrer", "text": COACH_PRESET_SPIRITUAL},
}

DEFAULT_COACH_PRESET_KEY = "therapist"
DEFAULT_COACH_PROMPT = COACH_PRESETS[DEFAULT_COACH_PRESET_KEY]["text"]


DEFAULT_SUMMARY_PROMPT = """Du erstellst aus dem vorausgegangenen Dialog zwischen Nutzer und Begleiter
einen klaren, strukturierten Tagebucheintrag in der Ich-Perspektive des
Nutzers.

Regeln:
- Verwende ausschließlich Inhalte, die der Nutzer im Dialog selbst genannt hat.
  Spiegelungen oder Fragen des Begleiters fließen NUR ein, wenn der Nutzer
  ihnen zugestimmt oder sie aufgegriffen hat.
- Erfinde keine Gefühle, Personen oder Ereignisse.
- Schreibe in vollständigen Sätzen, gegliedert in sinnvolle Absätze. Markdown
  ist erlaubt (Überschriften, Listen, Hervorhebungen sparsam).
- Bewahre den Ton und das Vokabular des Nutzers — nicht glätten, nicht
  literarischer machen, als er selbst geschrieben hat.
- Korrigiere Füllwörter, Grammatik und Rechtschreibung still im Hintergrund.
- Der Eintrag soll als persönlicher Rückblick lesbar sein, nicht als Protokoll
  des Chats."""


SUMMARY_JSON_SCHEMA_SUFFIX = """

---
Gib AUSSCHLIESSLICH JSON zurück, das folgendem Schema entspricht:

{{
  "title": "<prägnanter Titel, max. 80 Zeichen>",
  "content": "<vollständiger Eintrag in Markdown, Ich-Perspektive, Ton bewahrt>",
  "tags": ["<3-7 Schlagwörter, kleingeschrieben, keine Duplikate>"],
  "entry_date": "<YYYY-MM-DD, Standardwert: heute>"
}}

Verwende bevorzugt bereits existierende Tags, wenn sinnvoll: {existing_tags}.
Wenn der Nutzer ein explizites Datum erwähnt hat, nutze es."""
```

- [ ] **Step 2: Importe in abhängigen Modulen brechen lassen — kurz prüfen**

Run: `cd backend && .venv/bin/python -c "from app.services.prompts import COACH_PRESETS, DEFAULT_COACH_PROMPT, DEFAULT_SUMMARY_PROMPT, SUMMARY_JSON_SCHEMA_SUFFIX; print(list(COACH_PRESETS.keys()))"`
Expected: `['therapist', 'coach', 'stoic', 'spiritual']`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/prompts.py
git commit -m "feat(prompts): vier Coach-Personas + Summary-Default + JSON-Suffix als Konstanten"
```

---

## Task 2: SQLAlchemy-Modell — Felder umbenennen + ergänzen

**Files:**
- Modify: `backend/app/models/settings.py`

- [ ] **Step 1: `system_prompt` durch `coach_prompt` ersetzen, `summary_prompt` ergänzen**

In `backend/app/models/settings.py` die Zeile

```python
    system_prompt: Mapped[str | None] = mapped_column(Text)
```

ersetzen durch:

```python
    coach_prompt: Mapped[str | None] = mapped_column(Text)
    summary_prompt: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 2: Importprüfung — Modul muss laden (auch wenn andere Module noch alte Namen referenzieren, Modell-Modul selbst ist autark)**

Run: `cd backend && .venv/bin/python -c "from app.models.settings import AppSettings; print([c.name for c in AppSettings.__table__.columns if c.name.endswith('_prompt')])"`
Expected: `['coach_prompt', 'summary_prompt']`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/settings.py
git commit -m "feat(models): rename system_prompt → coach_prompt, add summary_prompt"
```

---

## Task 3: Alembic-Migration — Rename + Add

**Files:**
- Create: `backend/alembic/versions/a7c1e4f29b03_split_coach_summary_prompts.py`

- [ ] **Step 1: Aktuelle Head-Revision ermitteln**

Run: `cd backend && .venv/bin/alembic heads`
Expected: eine Zeile, z. B. `5efb3f0bd583 (head)`. Notiere den Hash als `<DOWN_REV>`.

- [ ] **Step 2: Migration anlegen**

Datei `backend/alembic/versions/a7c1e4f29b03_split_coach_summary_prompts.py`:

```python
"""split coach and summary prompts

Revision ID: a7c1e4f29b03
Revises: <DOWN_REV>
Create Date: 2026-04-28 12:00:00.000000

Renames AppSettings.system_prompt → coach_prompt (verlustfrei) und ergänzt
summary_prompt (NULLable). Downgrade dropt summary_prompt — dortiger Inhalt
geht verloren.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c1e4f29b03"
down_revision: str | Sequence[str] | None = "<DOWN_REV>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.alter_column("system_prompt", new_column_name="coach_prompt")
        batch.add_column(sa.Column("summary_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.drop_column("summary_prompt")
        batch.alter_column("coach_prompt", new_column_name="system_prompt")
```

`<DOWN_REV>` aus Step 1 einsetzen.

- [ ] **Step 3: Migration anwenden**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: Output endet mit `Running upgrade <DOWN_REV> -> a7c1e4f29b03, split coach and summary prompts`

- [ ] **Step 4: Schema-Check**

Run: `cd backend && .venv/bin/python -c "from app.db import engine; from sqlalchemy import inspect; print(sorted(c['name'] for c in inspect(engine).get_columns('settings') if c['name'].endswith('_prompt')))"`
Expected: `['coach_prompt', 'summary_prompt']`

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/a7c1e4f29b03_split_coach_summary_prompts.py
git commit -m "feat(db): migration to rename system_prompt and add summary_prompt"
```

---

## Task 4: Bootstrap — neue Felder

**Files:**
- Modify: `backend/app/bootstrap.py`

- [ ] **Step 1: Bestehenden Bootstrap-Code anpassen**

In `backend/app/bootstrap.py`:

Ersetze die Zeilen:

```python
from app.services.prompts import STRUCTURE_SYSTEM_PROMPT
```

durch (Import wird nicht mehr gebraucht):

```python
# (kein Prompt-Default beim Bootstrap — NULL bedeutet "DEFAULT_COACH_PROMPT zur Laufzeit")
```

und ersetze

```python
        db.add(
            AppSettings(
                id=1,
                password_hash=hash_password(env.app_password),
                system_prompt=STRUCTURE_SYSTEM_PROMPT or None,
            )
        )
```

durch

```python
        db.add(
            AppSettings(
                id=1,
                password_hash=hash_password(env.app_password),
                coach_prompt=None,
                summary_prompt=None,
            )
        )
```

- [ ] **Step 2: Bootstrap-Test anpassen**

In `backend/tests/test_bootstrap.py` jede Referenz auf `system_prompt` durch `coach_prompt` ersetzen, ggf. zusätzliche Assertion auf `summary_prompt is None` hinzufügen.

Run: `grep -n system_prompt backend/tests/test_bootstrap.py` — sollte leer sein.

- [ ] **Step 3: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/test_bootstrap.py -q`
Expected: alle PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/bootstrap.py backend/tests/test_bootstrap.py
git commit -m "feat(bootstrap): seed coach_prompt/summary_prompt as NULL"
```

---

## Task 5: Pydantic-Schemas — Settings + Chat

**Files:**
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/schemas/chat.py`

- [ ] **Step 1: `schemas/settings.py` aktualisieren**

`backend/app/schemas/settings.py` komplett ersetzen:

```python
from pydantic import BaseModel


class CoachPresetOut(BaseModel):
    key: str
    label: str
    text: str


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

    coach_prompt: str | None = None
    summary_prompt: str | None = None
    coach_presets: list[CoachPresetOut] = []
    default_coach_preset_key: str = "therapist"

    totp_enabled: bool = False


class SettingsPatch(BaseModel):
    stt_base_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = None
    chat_base_url: str | None = None
    chat_api_key: str | None = None
    chat_model: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None
    embed_model: str | None = None
    tts_base_url: str | None = None
    tts_api_key: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    tts_speed: float | None = None
    coach_prompt: str | None = None
    summary_prompt: str | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str
```

- [ ] **Step 2: `schemas/chat.py` aktualisieren**

`backend/app/schemas/chat.py`: Feld umbenennen.

```python
from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    coach_prompt_override: str | None = None


class FinalizeRequest(BaseModel):
    messages: list[ChatMessage]
```

- [ ] **Step 3: Importprüfung**

Run: `cd backend && .venv/bin/python -c "from app.schemas.settings import SettingsOut, SettingsPatch, CoachPresetOut; from app.schemas.chat import ChatRequest; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/settings.py backend/app/schemas/chat.py
git commit -m "feat(schemas): coach_prompt/summary_prompt + coach_presets in SettingsOut, rename ChatRequest field"
```

---

## Task 6: Chat-Service — Coach-Resolution + Summary mit Suffix

**Files:**
- Modify: `backend/app/services/chat.py`

- [ ] **Step 1: Datei komplett ersetzen**

```python
"""Chat streaming + finalize service. Coach-Prompt aus AppSettings.coach_prompt
(fällt auf DEFAULT_COACH_PROMPT zurück); Finalize konkateniert
AppSettings.summary_prompt (oder DEFAULT_SUMMARY_PROMPT) mit dem hardcoded
SUMMARY_JSON_SCHEMA_SUFFIX (inkl. {existing_tags}-Substitution).
"""
import json
from collections.abc import Iterator
from datetime import date

from app.db import SessionLocal
from app.models.settings import AppSettings
from app.models.tag import Tag
from app.services.llm_client import get_client
from app.services.prompts import (
    DEFAULT_COACH_PROMPT,
    DEFAULT_SUMMARY_PROMPT,
    SUMMARY_JSON_SCHEMA_SUFFIX,
)


def _coach_prompt(override: str | None) -> str:
    if override:
        return override
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        return s.coach_prompt if (s and s.coach_prompt) else DEFAULT_COACH_PROMPT


def _summary_prompt() -> str:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        body = s.summary_prompt if (s and s.summary_prompt) else DEFAULT_SUMMARY_PROMPT
    return body + SUMMARY_JSON_SCHEMA_SUFFIX


def stream_chat(
    messages: list[dict], coach_prompt_override: str | None = None
) -> Iterator[str]:
    client, model = get_client("chat")
    sys_msg = {"role": "system", "content": _coach_prompt(coach_prompt_override)}
    stream = client.chat.completions.create(
        model=model, messages=[sys_msg] + messages, stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


def _existing_tags() -> list[str]:
    with SessionLocal() as db:
        return [t.name for t in db.query(Tag).all()]


def finalize(messages: list[dict]) -> dict:
    """Run the finalize step with JSON-mode + graceful fallback.

    Some OpenAI-compatible servers (Ollama older builds) reject `response_format`
    with 400/422. We catch that and retry without JSON-mode, using a stricter
    system prompt. If parsing still fails, a second retry with an even stricter
    hint is attempted. If that fails, the JSONDecodeError propagates to the caller.
    """
    client, model = get_client("chat")
    system = _summary_prompt().format(existing_tags=_existing_tags())

    def _call(use_json_mode: bool, extra_hint: str = "") -> str:
        msgs = [{"role": "system", "content": system + extra_hint}] + messages
        kwargs: dict = {"model": model, "messages": msgs}
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or "{}"

    try:
        raw = _call(use_json_mode=True)
    except Exception as e:
        msg = str(e).lower()
        if "400" in msg or "422" in msg or "response_format" in msg or "unsupported" in msg:
            raw = _call(
                use_json_mode=False,
                extra_hint="\n\nAntworte AUSSCHLIESSLICH mit validem JSON. Kein Fließtext.",
            )
        else:
            raise

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raw2 = _call(
            use_json_mode=False,
            extra_hint="\n\nDeine Antwort MUSS exakt ein JSON-Objekt sein. Nichts anderes.",
        )
        obj = json.loads(raw2)

    obj.setdefault("entry_date", date.today().isoformat())
    return obj
```

**Wichtig:** `_summary_prompt()` baut den String mit `{existing_tags}`-Platzhalter; `format()`-Aufruf substitutiert ihn in `finalize()`. Geschweifte Klammern im JSON-Schema sind in `SUMMARY_JSON_SCHEMA_SUFFIX` mit `{{` / `}}` escaped — siehe Task 1.

- [ ] **Step 2: `routes/chat.py` anpassen**

In `backend/app/routes/chat.py` Zeile 21 ändern: `body.system_prompt_override` → `body.coach_prompt_override`.

- [ ] **Step 3: Importprüfung**

Run: `cd backend && .venv/bin/python -c "from app.services.chat import stream_chat, finalize, _coach_prompt, _summary_prompt; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat.py backend/app/routes/chat.py
git commit -m "feat(chat): split coach/summary prompts; hardcoded JSON-Suffix"
```

---

## Task 7: Settings-Route — Lesen/Schreiben + Preset-Liste

**Files:**
- Modify: `backend/app/routes/settings.py`

- [ ] **Step 1: Imports + `_settings_to_out` erweitern**

Am Datei-Anfang Import ergänzen:

```python
from app.services.prompts import COACH_PRESETS, DEFAULT_COACH_PRESET_KEY
```

und unterhalb `_mask` neue Helfer-Funktion vor `_settings_to_out`:

```python
def _coach_presets_payload() -> list[dict]:
    return [
        {"key": k, "label": v["label"], "text": v["text"]}
        for k, v in COACH_PRESETS.items()
    ]
```

In `_settings_to_out` die Zeile

```python
        system_prompt=s.system_prompt,
```

ersetzen durch:

```python
        coach_prompt=s.coach_prompt,
        summary_prompt=s.summary_prompt,
        coach_presets=_coach_presets_payload(),
        default_coach_preset_key=DEFAULT_COACH_PRESET_KEY,
```

- [ ] **Step 2: `update_settings` anpassen**

Den Block

```python
        if "system_prompt" in data:
            s.system_prompt = data["system_prompt"]
```

ersetzen durch:

```python
        for prompt_field in ("coach_prompt", "summary_prompt"):
            if prompt_field in data:
                raw = data[prompt_field]
                # Empty string / whitespace-only resets override → NULL
                # (Default-Prompt wird zur Laufzeit benutzt).
                if isinstance(raw, str) and raw.strip():
                    setattr(s, prompt_field, raw)
                else:
                    setattr(s, prompt_field, None)
```

- [ ] **Step 3: Importprüfung**

Run: `cd backend && .venv/bin/python -c "from app.routes.settings import router; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/settings.py
git commit -m "feat(settings): expose coach/summary prompts + preset list"
```

---

## Task 8: Bestehende Backend-Tests anpassen

**Files:**
- Modify: `backend/tests/test_chat.py`
- Modify: `backend/tests/test_finalize.py`
- Modify: `backend/tests/test_settings_routes.py`
- Modify: `backend/tests/test_settings_resolved_fields.py`

- [ ] **Step 1: `test_chat.py` — `system_prompt` durch `coach_prompt` ersetzen**

In `backend/tests/test_chat.py` Zeile 18:

```python
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), system_prompt="SYS"))
```

ändern zu:

```python
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), coach_prompt="SYS"))
```

- [ ] **Step 2: Globaler Sweep — alle übrigen `system_prompt`-Vorkommen in Tests prüfen**

Run: `grep -rn "system_prompt\|system_prompt_override" backend/tests/`
Erwartung: keine Treffer mehr. Falls doch, jeden Treffer auf `coach_prompt` / `coach_prompt_override` mappen oder (falls Test gegen `SettingsOut`-Feld) auf `coach_prompt` plus ggf. neue Assertions für `summary_prompt`/`coach_presets` ergänzen.

- [ ] **Step 3: `test_settings_routes.py` — neue Felder in GET-/PUT-Tests sicherstellen**

Datei öffnen: `backend/tests/test_settings_routes.py`. Jede Stelle, die `data.get("system_prompt")` o. ä. liest, an `coach_prompt` anpassen. Falls ein Test `system_prompt` per PUT setzt, das Feld in `coach_prompt` umbenennen.

Falls die Datei eine `SettingsOut`-Struktur als JSON erwartet, prüfen, dass beim GET-Test mindestens diese Assertion ergänzt wird (am Ende eines bestehenden GET-Tests):

```python
    assert "coach_presets" in data
    assert {p["key"] for p in data["coach_presets"]} == {"therapist", "coach", "stoic", "spiritual"}
    assert data["default_coach_preset_key"] == "therapist"
```

- [ ] **Step 4: Test-Suite laufen lassen**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle bisher grünen Tests bleiben grün. Falls einzelne Tests fehlschlagen mit `KeyError: 'system_prompt'` o. ä., genauer Fehlerort fixen (gleiches Pattern: rename → coach_prompt).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/
git commit -m "test: rename system_prompt → coach_prompt across existing tests"
```

---

## Task 9: Neue Tests in `test_prompts_split.py`

**Files:**
- Create: `backend/tests/test_prompts_split.py`

- [ ] **Step 1: Test-Datei anlegen**

```python
"""Tests für split coach/summary prompts (Spec 2026-04-28)."""
import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings
from app.models.tag import Tag
from app.services.chat import _coach_prompt, _summary_prompt
from app.services.prompts import (
    COACH_PRESETS,
    DEFAULT_COACH_PROMPT,
    DEFAULT_COACH_PRESET_KEY,
    DEFAULT_SUMMARY_PROMPT,
    SUMMARY_JSON_SCHEMA_SUFFIX,
)


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.query(Tag).delete()
        db.commit()


def _set(field: str, value):
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        setattr(s, field, value)
        db.commit()


def test_default_coach_prompt_used_when_db_empty():
    _set("coach_prompt", None)
    assert _coach_prompt(None) == DEFAULT_COACH_PROMPT


def test_custom_coach_prompt_used_when_set():
    _set("coach_prompt", "Du bist Yoda.")
    try:
        assert _coach_prompt(None) == "Du bist Yoda."
    finally:
        _set("coach_prompt", None)


def test_chat_request_override_wins_over_db():
    _set("coach_prompt", "DB-Wert")
    try:
        assert _coach_prompt("Override-Wert") == "Override-Wert"
    finally:
        _set("coach_prompt", None)


def test_default_summary_prompt_uses_default_plus_suffix():
    _set("summary_prompt", None)
    out = _summary_prompt()
    assert out.startswith(DEFAULT_SUMMARY_PROMPT)
    assert SUMMARY_JSON_SCHEMA_SUFFIX in out


def test_custom_summary_prompt_uses_user_text_plus_suffix():
    _set("summary_prompt", "Mein eigener Stil-Prompt.")
    try:
        out = _summary_prompt()
        assert out.startswith("Mein eigener Stil-Prompt.")
        assert SUMMARY_JSON_SCHEMA_SUFFIX in out
    finally:
        _set("summary_prompt", None)


def test_summary_prompt_format_substitutes_existing_tags():
    _set("summary_prompt", None)
    raw = _summary_prompt()
    formatted = raw.format(existing_tags=["reise", "arbeit"])
    assert "['reise', 'arbeit']" in formatted
    assert "{existing_tags}" not in formatted


def test_coach_presets_have_four_entries():
    assert set(COACH_PRESETS.keys()) == {"therapist", "coach", "stoic", "spiritual"}
    assert DEFAULT_COACH_PRESET_KEY == "therapist"


def test_settings_get_returns_coach_presets():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/settings", cookies={"session": sid, "csrf": "t"})
    assert r.status_code == 200
    data = r.json()
    assert {p["key"] for p in data["coach_presets"]} == {
        "therapist", "coach", "stoic", "spiritual",
    }
    assert data["default_coach_preset_key"] == "therapist"
    therapist = next(p for p in data["coach_presets"] if p["key"] == "therapist")
    assert "Therapeut" == therapist["label"]
    assert therapist["text"].startswith("Du bist ein einfühlsamer")


def test_settings_patch_empty_string_resets_coach_prompt_to_null():
    sid = create_session()
    _set("coach_prompt", "Mein eigener Prompt")
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"coach_prompt": ""},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).coach_prompt is None


def test_settings_patch_whitespace_only_resets_summary_prompt_to_null():
    sid = create_session()
    _set("summary_prompt", "X")
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"summary_prompt": "   \n   "},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).summary_prompt is None


def test_settings_patch_persists_non_empty_prompts():
    sid = create_session()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"coach_prompt": "Custom-Coach", "summary_prompt": "Custom-Summary"},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 200
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert s.coach_prompt == "Custom-Coach"
        assert s.summary_prompt == "Custom-Summary"
    _set("coach_prompt", None)
    _set("summary_prompt", None)


def test_finalize_uses_summary_prompt_with_existing_tags():
    """End-to-End: /api/chat/finalize benutzt _summary_prompt() inkl. Tag-Substitution."""
    sid = create_session()
    with SessionLocal() as db:
        db.merge(Tag(name="reise"))
        db.commit()

    captured = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "model": "gpt-4o-mini",
            "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps({
                    "title": "T", "content": "C", "tags": ["reise"],
                    "entry_date": "2026-04-28",
                })},
            }],
        })

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=_capture)
        with TestClient(app) as c:
            r = c.post(
                "/api/chat/finalize",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    sys_content = captured["body"]["messages"][0]["content"]
    assert "['reise']" in sys_content
    assert "{existing_tags}" not in sys_content
    assert "JSON" in sys_content  # Suffix wirklich angehängt
```

- [ ] **Step 2: Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest tests/test_prompts_split.py -v`
Expected: alle 12 Tests PASS.

- [ ] **Step 3: Volle Test-Suite zur Sicherheit**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle Tests grün.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_prompts_split.py
git commit -m "test: split coach/summary prompts coverage (12 tests)"
```

---

## Task 10: Frontend — Settings-Page mit zwei Sektionen + Preset-Buttons

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Type-Definition aktualisieren**

In `frontend/src/routes/settings/+page.svelte` (oben im `<script lang="ts">`-Block) den `SettingsOut`-Typ ersetzen.

Alt:

```ts
  type SettingsOut = {
    stt_base_url: string | null; stt_api_key_masked: string | null; stt_model: string | null;
    chat_base_url: string | null; chat_api_key_masked: string | null; chat_model: string | null;
    embed_base_url: string | null; embed_api_key_masked: string | null; embed_model: string | null;
    tts_base_url: string | null; tts_api_key_masked: string | null; tts_model: string | null;
    system_prompt: string | null;
    tts_voice: string | null; tts_speed: number | null;
    totp_enabled: boolean;
    stt_resolved_base_url: string | null; stt_resolved_model: string | null;
    chat_resolved_base_url: string | null; chat_resolved_model: string | null;
    embed_resolved_base_url: string | null; embed_resolved_model: string | null;
    tts_resolved_base_url: string | null; tts_resolved_model: string | null;
  };
```

Neu:

```ts
  type CoachPreset = { key: string; label: string; text: string };
  type SettingsOut = {
    stt_base_url: string | null; stt_api_key_masked: string | null; stt_model: string | null;
    chat_base_url: string | null; chat_api_key_masked: string | null; chat_model: string | null;
    embed_base_url: string | null; embed_api_key_masked: string | null; embed_model: string | null;
    tts_base_url: string | null; tts_api_key_masked: string | null; tts_model: string | null;
    coach_prompt: string | null;
    summary_prompt: string | null;
    coach_presets: CoachPreset[];
    default_coach_preset_key: string;
    tts_voice: string | null; tts_speed: number | null;
    totp_enabled: boolean;
    stt_resolved_base_url: string | null; stt_resolved_model: string | null;
    chat_resolved_base_url: string | null; chat_resolved_model: string | null;
    embed_resolved_base_url: string | null; embed_resolved_model: string | null;
    tts_resolved_base_url: string | null; tts_resolved_model: string | null;
  };
```

- [ ] **Step 2: Preset-Handler-Funktionen ergänzen**

Im `<script lang="ts">`-Block, nach `let msg: string | null = $state(null);`, ergänzen:

```ts
  function applyCoachPreset(preset: CoachPreset) {
    const current = (form.coach_prompt ?? s?.coach_prompt ?? "") as string;
    const isCustom =
      current.trim().length > 0 &&
      !s?.coach_presets.some((p) => p.text === current);
    if (isCustom && !confirm("Eigenen Coach-Prompt durch Vorlage ersetzen?")) return;
    form.coach_prompt = preset.text;
  }

  function clearCoachPrompt() {
    const current = (form.coach_prompt ?? s?.coach_prompt ?? "") as string;
    if (current.trim().length > 0 && !confirm("Textfeld leeren?")) return;
    form.coach_prompt = "";
  }

  function defaultCoachText(): string {
    const k = s?.default_coach_preset_key ?? "therapist";
    return s?.coach_presets.find((p) => p.key === k)?.text ?? "";
  }
```

- [ ] **Step 3: Markup ersetzen**

Im Template den Block

```svelte
    <label>
      System-Prompt
      <textarea bind:value={form.system_prompt} rows="6" placeholder={s.system_prompt ?? ""}></textarea>
    </label>
    <button type="button" onclick={saveEndpoints}>Speichern</button>
  </section>
```

ersetzen durch:

```svelte
    <fieldset class="prompt-section">
      <legend>Coach-Prompt (Reflexions-Dialog)</legend>
      <p class="muted">
        Der Coach begleitet dich beim Reflektieren — er strukturiert nichts und
        schreibt keinen Eintrag. Wähle eine Persona oder formuliere einen
        eigenen Prompt.
      </p>
      <div class="preset-buttons">
        {#each s.coach_presets as preset (preset.key)}
          <button type="button" onclick={() => applyCoachPreset(preset)}>
            {preset.label}
          </button>
        {/each}
        <button type="button" onclick={clearCoachPrompt}>Eigener Prompt</button>
      </div>
      <textarea
        bind:value={form.coach_prompt}
        rows="10"
        placeholder={s.coach_prompt ?? defaultCoachText()}
      ></textarea>
    </fieldset>

    <fieldset class="prompt-section">
      <legend>Zusammenfassungs-Prompt</legend>
      <p class="muted">
        Wenn du auf „Tagebucheintrag erstellen" klickst, baut dieses Modell aus
        eurem Dialog den fertigen Eintrag. Du kannst den Stil hier anpassen —
        die JSON-Struktur des Eintrags wird automatisch ergänzt.
      </p>
      <textarea
        bind:value={form.summary_prompt}
        rows="10"
        placeholder={s.summary_prompt ?? ""}
      ></textarea>
    </fieldset>

    <button type="button" onclick={saveEndpoints}>Speichern</button>
  </section>
```

- [ ] **Step 4: CSS-Snippet am Ende der `<style>`-Sektion ergänzen**

In den existierenden `<style>`-Block der Datei (am Ende):

```css
  .prompt-section { margin-top: 1rem; }
  .prompt-section legend { font-weight: 600; }
  .preset-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.4rem 0 0.6rem;
  }
  .preset-buttons button {
    padding: 0.3rem 0.7rem;
    font-size: 0.9rem;
  }
```

- [ ] **Step 5: TypeCheck + Build**

Run: `cd frontend && npm run check`
Expected: 0 errors, 0 warnings (oder mindestens keine neuen).

Run: `cd frontend && npm run build`
Expected: erfolgreicher Build.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/settings/+page.svelte
git commit -m "feat(ui): zwei Prompt-Sektionen mit vier Coach-Preset-Buttons"
```

---

## Task 11: Volle Verifikation lokal

**Files:** keine

- [ ] **Step 1: Backend-Tests komplett**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle Tests grün, inkl. `test_prompts_split.py`.

- [ ] **Step 2: Frontend-Tests komplett**

Run: `cd frontend && npm test -- --run`
Expected: alle Tests grün.

- [ ] **Step 3: Frontend-Typecheck**

Run: `cd frontend && npm run check`
Expected: 0 errors.

- [ ] **Step 4: Stack neu hochziehen + manueller Smoketest**

Run: `docker compose -f deploy/docker-compose.yml down && docker compose -f deploy/docker-compose.yml up -d --build`

Im Browser:
1. `/settings` öffnen → zwei Sektionen sichtbar (Coach + Zusammenfassung), vier Persona-Buttons + „Eigener Prompt"-Button.
2. Klick auf „Stoiker" füllt Coach-Textarea mit Stoiker-Text.
3. Klick auf „Eigener Prompt" leert das Coach-Textarea.
4. Speichern → Reload → leerer Coach-Prompt zeigt Therapist-Default als Placeholder.
5. `/new` → Eintrag tippen → erste LLM-Antwort spiegelt + fragt, **strukturiert nicht**.
6. Button „Tagebucheintrag erstellen" → Modal mit strukturiertem Eintrag erscheint.

- [ ] **Step 5: Roadmap aktualisieren**

In `~/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md` unter „✅ Erledigt" einen Eintrag ergänzen:

```
### Split Coach/Summary-Prompts (2026-04-28)
- Spec: docs/superpowers/specs/2026-04-28-split-coach-summary-prompts-design.md
- Plan: docs/superpowers/plans/2026-04-28-split-coach-summary-prompts.md
- Migration a7c1e4f29b03 rename system_prompt → coach_prompt + add summary_prompt
- Vier Coach-Personas (Therapeut/Coach/Stoiker/Spirituell) als Vorlagen-Buttons in /settings
- JSON-Schema-Suffix für Finalize hardcoded → Nutzer kann Schema nicht zerschießen
```

- [ ] **Step 6: Commit Verifikations-Artefakte falls Code-Anpassungen aus Smoketest**

```bash
git add -u
git commit -m "chore: roadmap updaten + smoketest-fixes (falls Code-Änderungen)"
```

---

## Self-Review-Notiz

- Spec § Architektur Backend Items 1-6 → Tasks 1, 2/3, 5, 5, 6, 6.
- Spec § Architektur Frontend Items 1-3 → Task 10. Item 3 (`coach_prompt_override` im /new-Flow) ist No-Op, weil der heutige Frontend-Code nie ein Override mitschickt — Backend-Schema-Rename in Task 5 deckt den API-Vertrag.
- Spec § Tests → Task 9 (12 Tests, deckt alle aufgelisteten Akzeptanz-Kriterien ab) + Task 8 (Anpassung bestehender Tests).
- Spec § Migration → Task 3.
- Anhang A (Preset-Texte) → wortgleich in Task 1.
