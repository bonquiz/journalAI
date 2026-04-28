# Split Coach- und Summary-Prompts mit Persona-Presets

**Status:** Draft
**Datum:** 2026-04-28
**Autor:** Julian (via Claude-Brainstorm)

## Problem

Der aktuelle Chat-Flow auf `/new` benutzt einen einzigen System-Prompt
(`STRUCTURE_SYSTEM_PROMPT` in `backend/app/services/prompts.py`), der das LLM
gleichzeitig dazu anweist, den Text **strukturiert zu spiegeln** und
**Reflexionsfragen** zu stellen. Effekt: Schon in der ersten Antwort
liefert das Modell einen strukturierten Entwurf des Tagebucheintrags, was
sich nicht wie ein offener Reflexions-Dialog anfühlt.

Der Nutzer möchte beim Hin-und-Her mit dem LLM einen einfühlsamen Begleiter
(„Therapeut", „Coach" etc.), der **nicht strukturiert, nicht zusammenfasst**
und keinen Eintrag schreibt. Erst beim Klick auf **„Tagebucheintrag erstellen"**
soll ein zweiter, klar getrennter Schritt aus dem Dialog einen
strukturierten Eintrag bauen — wie heute schon der `FINALIZE_SYSTEM_PROMPT`,
nur mit nutzer-editierbarem Stil/Ton-Anteil.

Außerdem soll der Coach-Prompt mit **vorgefertigten Personas** (Buttons)
schnell umschaltbar sein, ohne dass der Nutzer den Prompt selbst formulieren
muss — er kann aber jeden geladenen Preset-Text frei editieren.

## Ziel

1. Den heutigen Single-Prompt in zwei voneinander unabhängige Prompts auftrennen:
   `coach_prompt` (Chat-Streaming) und `summary_prompt` (Finalize-Schritt).
2. Beide Prompts in den Settings (`/settings`) **separat editierbar** machen.
3. Für den `coach_prompt` vier eingebaute **Persona-Presets**
   (Therapeut · Coach · Stoiker · Spiritueller Lehrer) plus Button
   „Eigener Prompt", der das Feld leert. Klick auf eine Persona lädt deren
   Text ins Textarea (überschreibbar, danach editierbar).
4. Für den `summary_prompt` einen einzigen Default (kein Preset-Switching).
   Das JSON-Schema-Korsett (`title/content/tags/entry_date`,
   `existing_tags`-Platzhalter) bleibt **unsichtbar im Backend** und wird
   beim Finalize automatisch an den nutzer-editierbaren Stil-Anteil
   angehängt — der Nutzer kann das Schema nicht zerschießen.
5. Bestehende DB-Inhalte (`AppSettings.system_prompt`) verlustfrei migrieren.

## Nicht-Ziele

- Keine Editier-UI für das JSON-Schema-Korsett selbst.
- Keine Presets für `summary_prompt`.
- Keine Versionierung / History von Prompts.
- Kein Per-Eintrag-Override (ChatRequest behält den `system_prompt_override`-
  Mechanismus, der bleibt unverändert).
- Keine Änderungen am STT/TTS/Embed-Flow oder an der Auth.

## Architektur

### Backend

#### 1. `app/services/prompts.py` — Konstanten

Bestehende Konstanten ersetzen durch:

```python
# Coach-Personas (Default = THERAPIST). Frei editierbar in /settings.
COACH_PRESET_THERAPIST = """…"""   # voller Text, siehe Anhang A
COACH_PRESET_COACH     = """…"""
COACH_PRESET_STOIC     = """…"""
COACH_PRESET_SPIRITUAL = """…"""

COACH_PRESETS: dict[str, dict[str, str]] = {
    "therapist": {"label": "Therapeut",          "text": COACH_PRESET_THERAPIST},
    "coach":     {"label": "Coach",              "text": COACH_PRESET_COACH},
    "stoic":     {"label": "Stoiker",            "text": COACH_PRESET_STOIC},
    "spiritual": {"label": "Spiritueller Lehrer","text": COACH_PRESET_SPIRITUAL},
}
DEFAULT_COACH_PRESET_KEY = "therapist"
DEFAULT_COACH_PROMPT     = COACH_PRESETS[DEFAULT_COACH_PRESET_KEY]["text"]

# Summary: nutzer-editierbarer Stil-Anteil + unsichtbares JSON-Korsett.
DEFAULT_SUMMARY_PROMPT = """…"""   # voller Text, siehe Anhang A

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

`STRUCTURE_SYSTEM_PROMPT` und `FINALIZE_SYSTEM_PROMPT` werden entfernt.
Alle Imports anpassen.

#### 2. `app/models/settings.py` + Migration

`AppSettings.system_prompt` (Text) wird zu `coach_prompt` (Text) **umbenannt**.
Neues Feld `summary_prompt` (Text, nullable).

Alembic-Migration `<rev>_split_coach_summary_prompts.py`:

- `op.batch_alter_table("settings")`:
  - `alter_column("system_prompt", new_column_name="coach_prompt")`
  - `add_column(Column("summary_prompt", Text, nullable=True))`
- Downgrade: umgekehrt, `summary_prompt`-Inhalt geht verloren (best effort,
  in Docstring vermerkt).

Kein Daten-Move nötig: bestehender Inhalt in `system_prompt` wandert durch
das Rename direkt nach `coach_prompt`.

#### 3. `app/schemas/settings.py`

`SettingsOut` und `SettingsPatch`:

- `system_prompt: str | None` → entfernen.
- Hinzufügen: `coach_prompt: str | None`, `summary_prompt: str | None`.
- Außerdem in `SettingsOut`: `coach_presets: list[CoachPresetOut]`
  (`{key, label, text}`-Liste), gefüllt aus `COACH_PRESETS`.
  Liefert die Backend-Wahrheit ans Frontend, damit Preset-Texte ohne
  Frontend-Deploy änderbar sind.

#### 4. `app/services/chat.py`

- `_system_prompt(override)` umbenannt zu `_coach_prompt(override)`,
  liest `s.coach_prompt`, fällt auf `DEFAULT_COACH_PROMPT` zurück.
- `stream_chat()` benutzt `_coach_prompt`.
- `finalize()` baut den Prompt aus DB-`summary_prompt` (oder
  `DEFAULT_SUMMARY_PROMPT` als Fallback) **plus** `SUMMARY_JSON_SCHEMA_SUFFIX`
  mit `{existing_tags}`-Substitution. Das Suffix ist hardcoded und nicht
  editierbar.

#### 5. `app/routes/settings.py`

- `_settings_to_out` füllt `coach_prompt`, `summary_prompt`, `coach_presets`.
- `update_settings`: für `coach_prompt` und `summary_prompt` das gleiche
  „Empty/Whitespace → NULL"-Pattern wie bei `tts_voice` (leeres Feld =
  Default verwenden).

Kein neuer Endpoint nötig — Presets reisen über `GET /api/settings` mit.

#### 6. `app/schemas/chat.py`

`ChatRequest.system_prompt_override` umbenennen zu `coach_prompt_override`
(API-Konsistenz). Frontend muss mit umziehen.

### Frontend

#### 1. `frontend/src/routes/settings/+page.svelte`

Zwei Sektionen statt der heutigen einen System-Prompt-Sektion:

**Sektion „Coach-Prompt"** (Reflexions-Dialog beim Schreiben)
- Erklär-Text: „Der Coach begleitet dich beim Reflektieren — er strukturiert
  nichts und schreibt keinen Eintrag. Wähle eine Persona oder formuliere
  einen eigenen Prompt."
- Button-Reihe: ein Button pro `coach_presets`-Eintrag (Label aus Backend)
  + Button **„Eigener Prompt"** (leert das Feld).
- `<textarea bind:value={form.coach_prompt} rows="10">` mit
  `placeholder={s.coach_prompt ?? <Default-Preset-Text>}`.
- Confirm-Dialog beim Preset-Klick, wenn `form.coach_prompt` gefüllt **und**
  nicht identisch zu einem der bekannten Preset-Texte ist
  (verhindert versehentliches Überschreiben eigener Edits).
- Speichern wie heute via PATCH `/api/settings`. Leeres Feld = Default
  (Therapeut) zur Laufzeit.

**Sektion „Zusammenfassungs-Prompt"** (Erstellung des Eintrags)
- Erklär-Text: „Wenn du auf ‚Tagebucheintrag erstellen' klickst, baut
  dieses Modell aus eurem Dialog den fertigen Eintrag. Du kannst den Stil
  hier anpassen — die JSON-Struktur des Eintrags wird automatisch
  ergänzt."
- Keine Buttons.
- `<textarea bind:value={form.summary_prompt} rows="10">` mit
  `placeholder={s.summary_prompt ?? <Default-Summary-Text>}`.

Alter `system_prompt`-Block wird ersatzlos durch diese beiden ersetzt.

#### 2. `$lib/api/types` (oder analoges Type-File)

`SettingsOut`-Typdefinition aktualisieren: `system_prompt` raus,
`coach_prompt`, `summary_prompt`, `coach_presets` rein.

#### 3. `frontend/src/routes/new/+page.svelte` (falls nötig)

Falls dort `system_prompt_override` an `/api/chat` mitgegeben wird:
Feldname umbenennen auf `coach_prompt_override`. Nach
`grep -r system_prompt_override frontend/src` prüfen.

### Datenfluss-Skizze

```
/new → POST /api/chat (messages, optional coach_prompt_override?)
       └─ services/chat.stream_chat
            └─ _coach_prompt() → DB.coach_prompt OR DEFAULT_COACH_PROMPT
            → SSE-Stream

[User klickt "Tagebucheintrag erstellen"]

/new → POST /api/chat/finalize (messages)
       └─ services/chat.finalize
            └─ DB.summary_prompt OR DEFAULT_SUMMARY_PROMPT
              + SUMMARY_JSON_SCHEMA_SUFFIX.format(existing_tags=…)
            → JSON-Mode-Call → Eintrag-Vorschau
```

## Migration & Backwards-Compat

- **DB-Migration** (Alembic): rename `system_prompt` → `coach_prompt`,
  add `summary_prompt`. Bestehende Custom-Inhalte bleiben automatisch
  als Coach-Prompt erhalten.
- **API-Bruch**: Settings-Endpoint liefert nicht mehr `system_prompt`,
  Frontend muss synchron deployen. Da journalAI single-tenant self-hosted
  ist und Frontend+Backend immer als Compose-Stack zusammen deployed
  werden, ist das unkritisch.
- **`coach_prompt_override` in `ChatRequest`**: alter Feldname
  `system_prompt_override` wird ohne Deprecation-Phase entfernt
  (gleiches Argument).

## Tests

### Backend (`backend/.venv/bin/pytest -q`)

Neue Tests in `tests/test_prompts_split.py` und Erweiterungen:

- `test_default_coach_prompt_used_when_db_empty` — `coach_prompt=NULL` →
  `_coach_prompt()` gibt `DEFAULT_COACH_PROMPT` zurück.
- `test_custom_coach_prompt_used_when_set` — Override greift.
- `test_chat_request_override_wins_over_db` — Request-Param hat Vorrang.
- `test_default_summary_prompt_appended_with_json_suffix` — Finalize
  baut Prompt = `DEFAULT_SUMMARY_PROMPT + SUMMARY_JSON_SCHEMA_SUFFIX`
  mit substituierten `existing_tags`.
- `test_custom_summary_prompt_uses_user_text_plus_suffix` — wenn DB-Wert
  gesetzt, wird der genommen, Suffix wird IMMER angehängt.
- `test_settings_get_returns_coach_presets` — `coach_presets`-Array
  enthält genau 4 Einträge mit korrekten Keys.
- `test_settings_patch_empty_string_resets_prompt_to_null` — leerer String
  → DB-NULL (parallel zu `tts_voice`).
- `test_settings_patch_whitespace_only_resets_prompt_to_null`.
- Migration-Test: nach Upgrade existiert `coach_prompt` mit altem
  `system_prompt`-Inhalt; `summary_prompt` ist NULL.

### Frontend (`cd frontend && npm test -- --run`)

- Settings-Page: Klick auf jeden Preset-Button füllt Textarea mit
  korrespondierendem `coach_presets[i].text`.
- Klick auf „Eigener Prompt" leert das Textarea.
- Confirm-Dialog erscheint, wenn Textarea Custom-Inhalt enthält und ein
  Preset-Button geklickt wird.
- Save sendet `coach_prompt` und `summary_prompt` korrekt.
- Save mit leerem Feld sendet leeren String (Backend resettet auf NULL).

### E2E (manuell, optional Playwright)

- /new → Chat-Verlauf zeigt **keine** Strukturierung in der ersten LLM-
  Antwort, sondern Spiegelung + 1-2 Fragen.
- Klick „Tagebucheintrag erstellen" → strukturierter Entwurf erscheint
  im Preview-Modal.
- /settings → Preset-Switch funktioniert, Speichern persistiert.

## Risiken

- **Modell-Compliance**: Schwächere lokale LLMs (qwen2.5:3b) ignorieren
  Anweisungen, „nichts zu strukturieren", und liefern trotzdem Listen.
  Nicht durch Code lösbar — in `docs/self-hosting.md` Hinweis ergänzen,
  dass für brauchbares Coaching ≥7b Modelle empfohlen sind (passt zur
  bestehenden „LLM-Qualitätsbar"-Memo).
- **Suffix-Kollision**: Wenn Nutzer eigenen Summary-Prompt schreibt, der
  selbst JSON-Schema-Anweisungen enthält, doppelt der hardcoded Suffix.
  Akzeptabel — das Modell ignoriert Redundanz, und der Default-Text
  enthält bewusst keine Schema-Anweisungen.
- **Bestehende Sessions**: Frontend-Cache von `SettingsOut` enthält ggf.
  noch `system_prompt`. Hard-Reload nach Deploy klärt das; SPA-Reload-
  Verhalten ist eh durch Auth-Redirect erzwungen.

---

## Anhang A — Volle Preset-Texte

### Coach-Preset 1: Therapeut *(Default)*

```
Du bist ein einfühlsamer Begleiter beim Tagebuchschreiben — im Stil eines
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
über "Tagebucheintrag erstellen" zur Zusammenfassung kommt.
```

### Coach-Preset 2: Coach

```
Du bist ein klarer, lösungsorientierter Coach, der dem Nutzer beim
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
Button "Tagebucheintrag erstellen" hin.
```

### Coach-Preset 3: Stoiker

```
Du bist ein nüchterner Begleiter im Geist der stoischen Philosophie
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
Button "Tagebucheintrag erstellen" hin.
```

### Coach-Preset 4: Spiritueller Lehrer

```
Du bist ein ruhiger spiritueller Begleiter im Geist von Lehrern wie
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
Button "Tagebucheintrag erstellen" hin.
```

### Summary-Default (Stil/Ton-Teil)

```
Du erstellst aus dem vorausgegangenen Dialog zwischen Nutzer und Begleiter
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
  des Chats.
```
