# journalAI — Phase 1 MVP Design

**Status:** Draft
**Datum:** 2026-04-14
**Scope:** Phase 1 (Core Backend + responsive Web-Frontend)
**Folgephasen (separate Specs):** Phase 2 semantische Suche · Phase 3 TTS-Vorlesen

## 1. Ziel und Kontext

Eine selbst gehostete, Open-Source-Tagebuch-App für eine einzelne Person. Der Nutzer erfasst Einträge per Diktat (Voice) oder Tastatur im Browser. Ein LLM strukturiert den Rohtext, stellt reflektierende Fragen, und speichert nach Bestätigung einen finalen Eintrag mit Titel, Text, Tags und Datum. Einträge lassen sich chronologisch durchsuchen, nach Tags filtern und editieren.

Die App ist als einzelner Docker-Compose-Stack ausgeliefert. Alle externen AI-Fähigkeiten (Speech-to-Text, Chat, Embeddings, Text-to-Speech) werden über OpenAI-kompatible HTTP-Endpoints angesprochen. Cloud-Nutzung (OpenAI-Key) und komplett lokale Setups (Ollama + faster-whisper-server + Piper/Kokoro) werden gleichwertig unterstützt.

## 2. Nicht-Ziele

- Multi-User / Mandantenfähigkeit.
- Native Mobile-App (eine installierbare PWA genügt).
- Echte End-to-End-Verschlüsselung (Server muss Klartext sehen, um LLM-Workflows auszuführen). Schutz erfolgt durch Transport-Sicherheit und At-Rest-Verschlüsselung.
- Volltext- oder semantische Suche (kommt in Phase 2).
- Einträge vorlesen (kommt in Phase 3).
- Export- / Import-Funktionen (separat zu entscheiden).

## 3. Architektur-Übersicht

Drei Docker-Container, orchestriert via `docker-compose.yml`:

```
              ┌──────────────────────────────────┐
              │  Caddy (Reverse-Proxy, HTTPS)    │
              │  :80/:443  Let's Encrypt         │
              └─────┬────────────────────┬───────┘
                    │                    │
              ┌─────▼──────┐      ┌──────▼──────┐
              │ Frontend   │      │  Backend    │
              │ SvelteKit  │      │  FastAPI    │
              │ (Nginx)    │      │  (Python)   │
              └────────────┘      └─────┬───────┘
                                        │
                   ┌────────────────────┼────────────────────┐
                   │                    │                    │
             ┌─────▼──────┐      ┌──────▼──────┐      ┌──────▼────────┐
             │ SQLite +   │      │  STT        │      │ Chat /        │
             │ SQLCipher  │      │ (Whisper    │      │ (Embed /      │
             │ Volume     │      │  kompatibel)│      │  TTS später)  │
             └────────────┘      └─────────────┘      └───────────────┘
```

- Caddy stellt unter einer Domain HTTPS bereit; leitet `/api/*` an Backend, alles andere an Frontend.
- Backend hält die einzige Datenbank-Verbindung (SQLite-Datei, SQLCipher-verschlüsselt, im Volume `./data/`).
- Externe AI-Endpoints sind **nicht Teil** des Stacks — der Nutzer entscheidet (Cloud, lokal, gemischt).

### 3.1 Repo-Struktur

```
journalAI/
├── backend/              (FastAPI, Dockerfile, Tests)
├── frontend/             (SvelteKit, Dockerfile, Tests)
├── deploy/
│   ├── docker-compose.yml
│   ├── Caddyfile
│   └── .env.example
├── docs/
│   ├── superpowers/specs/
│   ├── hardware-profiles.md
│   ├── endpoint-compatibility.md
│   └── self-hosting.md
├── .gitignore
├── LICENSE (MIT)
└── README.md
```

## 4. Datenmodell

SQLite mit SQLCipher (symmetrische Schlüssel-ableitung aus `DB_ENCRYPTION_KEY` in `.env`).

```sql
CREATE TABLE entries (
  id              TEXT PRIMARY KEY,             -- UUID v4
  entry_date      DATE NOT NULL,
  title           TEXT NOT NULL,
  content         TEXT NOT NULL,                -- Markdown
  raw_transcript  TEXT,                         -- Original-STT-Output
  chat_history    TEXT,                         -- JSON-Array des Dialogs
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_entries_date ON entries(entry_date DESC);

CREATE TABLE tags (
  name TEXT PRIMARY KEY
);

CREATE TABLE entry_tags (
  entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  tag_name TEXT NOT NULL REFERENCES tags(name)  ON DELETE CASCADE,
  PRIMARY KEY (entry_id, tag_name)
);
CREATE INDEX idx_entry_tags_tag ON entry_tags(tag_name);

CREATE TABLE settings (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  stt_base_url    TEXT, stt_api_key   TEXT, stt_model   TEXT,
  chat_base_url   TEXT, chat_api_key  TEXT, chat_model  TEXT,
  embed_base_url  TEXT, embed_api_key TEXT, embed_model TEXT,
  tts_base_url    TEXT, tts_api_key   TEXT, tts_model   TEXT,
  system_prompt   TEXT,
  totp_secret     TEXT,
  password_hash   TEXT NOT NULL
);

CREATE TABLE sessions (
  id               TEXT PRIMARY KEY,             -- opaker Cookie-Token
  created_at       TIMESTAMP NOT NULL,
  last_activity_at TIMESTAMP NOT NULL,
  expires_at       TIMESTAMP NOT NULL
);
```

Das Settings-Objekt ist immer genau eine Zeile (`id=1`). API-Keys werden bei `GET /api/settings` maskiert (nur die letzten vier Zeichen sichtbar).

Phase 2 ergänzt (nicht jetzt): `entry_embeddings` via `sqlite-vec`.

## 5. Backend

**Stack:** Python ≥ 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic Settings, argon2-cffi, pyotp, pysqlcipher3, `openai` SDK (für alle OpenAI-kompatiblen Endpoints), slowapi (Rate-Limiting), respx (Tests).

### 5.1 Modulstruktur

```
backend/app/
├── main.py              Routing, Middleware-Stack
├── config.py            Pydantic Settings (ENV-Overrides)
├── db.py                SQLCipher-Engine, Session-Factory, Alembic-Bootstrap
├── models/              SQLAlchemy: Entry, Tag, Settings, Session
├── auth/                Passwort-Hash, Session-Mgmt, TOTP
├── routes/
│   ├── auth.py          /auth/login, /logout, /totp/*
│   ├── entries.py       /entries CRUD, /tags
│   ├── transcribe.py    /transcribe
│   ├── chat.py          /chat (SSE), /chat/finalize
│   ├── settings.py      /settings GET/PUT, /health
├── services/
│   ├── stt.py           OpenAI-kompatibler STT-Client
│   ├── llm.py           Chat + JSON-Mode
│   └── prompts.py       Default-System-Prompts
└── security.py          CSRF, Rate-Limits, Secret-Management
```

### 5.2 Session & Auth

- Login via Passwort (argon2). Falls TOTP aktiviert, verlangt das Formular einen zweiten Faktor.
- Erfolgreiche Anmeldung erstellt eine Zeile in `sessions` und setzt ein opakes Cookie (`HttpOnly`, `Secure`, `SameSite=Strict`).
- **Idle-Timeout (Default 10 Min, ENV: `SESSION_IDLE_MINUTES`):** Middleware prüft `last_activity_at` bei jedem Request. Bei Überschreitung → Session löschen, 401.
- **Absolute-Timeout (Default 12 h, ENV: `SESSION_ABSOLUTE_HOURS`):** harte Obergrenze, unabhängig von Aktivität.
- Jeder erfolgreich authentifizierte Request aktualisiert `last_activity_at`.
- `POST /auth/logout` löscht die Session-Zeile zusätzlich zum Cookie.
- Nach Passwortwechsel oder TOTP-Aktivierung werden alle anderen Sessions invalidiert.
- CSRF-Schutz via Double-Submit-Token für schreibende Requests.
- Rate-Limits: `/auth/login` (5/min/IP), `/transcribe` (20/min), `/chat` (60/min).

### 5.3 LLM-Services

`services/llm.py` und `services/stt.py` sind dünne Wrapper über das `openai`-SDK. Jede Fähigkeit hat ein eigenes `OpenAI(base_url=…, api_key=…)`-Objekt, das aus dem aktuellen Settings-Row gebaut wird (ENV als Default).

- **STT:** `client.audio.transcriptions.create(file=…, model=…)` — kompatibel mit OpenAI, faster-whisper-server, whisper.cpp server.
- **Chat:** `client.chat.completions.create(…, stream=True)` — SSE zum Frontend.
- **Finalize:** `response_format={"type":"json_object"}` + Finalize-System-Prompt → garantiertes JSON `{title, content, tags[], entry_date}`.
- Bei ungültigem JSON: einmaliger Auto-Retry mit strengerer System-Message; danach 500 an den Client.

### 5.4 API

| Method | Path | Auth | Zweck |
|---|---|---|---|
| `POST` | `/api/auth/login` | – | Passwort (+ TOTP) → Cookie |
| `POST` | `/api/auth/logout` | ja | Cookie + Session-Row invalidieren |
| `POST` | `/api/auth/totp/setup` | ja | Secret + QR zurück |
| `POST` | `/api/auth/totp/confirm` | ja | TOTP aktivieren |
| `POST` | `/api/transcribe` | ja | Multipart Audio → `{transcript}` |
| `POST` | `/api/chat` | ja | `{messages, system_prompt?}` → SSE |
| `POST` | `/api/chat/finalize` | ja | Dialog → `{title, content, tags[], entry_date}` |
| `GET` | `/api/entries?tags=&q=&offset=&limit=` | ja | Liste, chronologisch absteigend |
| `POST` | `/api/entries` | ja | Eintrag anlegen |
| `GET` | `/api/entries/{id}` | ja | Detail |
| `PUT` | `/api/entries/{id}` | ja | Editieren |
| `DELETE` | `/api/entries/{id}` | ja | Löschen |
| `GET` | `/api/tags` | ja | Alle Tags (Filter/Autocomplete) |
| `GET` | `/api/settings` | ja | Settings (Keys maskiert) |
| `PUT` | `/api/settings` | ja | Settings aktualisieren |
| `GET` | `/api/health` | – | Ping + Reachability-Check der Endpoints |

Audio-Upload-Limit: 25 MB (ENV `MAX_UPLOAD_MB`). Audio-Dateien werden **nach Transkription verworfen** (Datenschutz).

## 6. Frontend

**Stack:** SvelteKit mit `@sveltejs/adapter-static`, TypeScript, Vitest, Playwright, Service-Worker für PWA.

### 6.1 Routen

- `/login` — Passwort + TOTP
- `/` — Home mit zwei Buttons („Eintrag erfassen" / „Einträge ansehen")
- `/new` — Aufnahme / Chat-Dialog / Final-Preview
- `/entries` — Liste, chronologisch absteigend, Filter-Chips für Tags, Textsuche (Substring in Titel/Content, Phase 1)
- `/entries/[id]` — Detailansicht mit Edit-Modus (Titel, Text, Datum, Tags — alles editierbar)
- `/settings` — Endpoints, System-Prompt-Override, Passwort ändern, TOTP verwalten, Session-Limits (read-only)

### 6.2 Kernkomponente `TextOrVoiceInput`

Überall dort einsetzbar, wo der Nutzer Text eingeben kann. Kombiniert `<textarea>` mit einem Mikrofon-Toggle. Klick startet `MediaRecorder`, erneuter Klick stoppt; das Audio-Blob geht an `/api/transcribe`, das Transkript wird in die Textarea eingefügt (vollständig editierbar). Senden erfolgt erst nach einem expliziten „Senden"-Klick.

Wird verwendet bei: initialer Eintrag-Eingabe, jeder Chat-Nachricht im Dialog, Editieren von Einträgen, Suchfeld (vorbereitend für Phase 2).

### 6.3 New-Entry-Flow

1. `TextOrVoiceInput` für den ersten Text / das erste Diktat.
2. Bei Absenden: POST `/api/chat` (SSE-Stream). Chat-UI zeigt Antwort streamend. State lebt in einem Svelte-Store `chatDraft`, nicht in der DB.
3. Nutzer kann beliebig viele Runden chatten. Der Mikrofon-Button ist in jeder Nachricht verfügbar.
4. Button „Eintrag jetzt speichern" ruft `/api/chat/finalize` mit dem gesamten Dialog. Antwort: strukturiertes JSON.
5. **Preview-Modal:** Datum (editierbar), Titel (editierbar), Markdown-Render des Contents, Tag-Chips (entfernbar, neue per Autocomplete aus `/api/tags` hinzufügbar). Buttons: „So speichern" | „Zurück zum Chat".
6. Bei Bestätigung: `POST /api/entries` mit `{title, content, tags, entry_date, raw_transcript, chat_history}`.

### 6.4 Einträge-Liste und Detail

- Unendliches Scrollen (oder einfaches Paging mit `offset/limit=50`).
- Filterleiste: Tag-Chips (multi-select, AND-Verknüpfung), Textfeld für Substring-Suche.
- Karten zeigen Datum, Titel, erste ~150 Zeichen Text, Tags.
- Detail-Ansicht mit Edit-Button → Formular mit denselben Feldern.

### 6.5 Session-UI

- In der Shell oben rechts: Countdown-Label „Automatische Abmeldung in MM:SS". Svelte-Store mit 1-Sekunden-Interval, Reset bei jedem `click`, `keydown`, `touchstart`.
- Bei ≤ 60 s Rest: Modal „In 60 Sekunden werden Sie abgemeldet. Aktiv bleiben?" Bestätigungs-Button sendet einen leichten Heartbeat-Request (`GET /api/health` reicht aus, weil er authentifiziert läuft).
- Bei 401 vom Server: Stores leeren (speziell `chatDraft`, damit entstehender Eintrag nicht in den Anmelde-Bildschirm mitgenommen wird), Redirect `/login`.

### 6.6 PWA

- `static/manifest.webmanifest` mit Name, Icons, `display: standalone`.
- `service-worker.js`: Cache-first für statische Assets, Network-only für `/api/*`.
- Ergebnis: auf dem Handy per „Zum Startbildschirm hinzufügen" installierbar.

## 7. LLM-Workflow-Prompts

Beide Prompts sind als Defaults im Code hinterlegt und in `/settings` überschreibbar.

**`STRUCTURE_SYSTEM_PROMPT`** (Dialog):

```
Du bist ein Assistent, der dem Nutzer hilft, Tagebucheinträge
klar zu strukturieren, ohne Inhalte zu verfälschen oder hinzuzufügen.

Regeln:
- Arbeite ausschließlich mit dem, was der Nutzer gesagt hat.
- Keine Fakten, Gefühle oder Interpretationen erfinden.
- Korrigiere Füllwörter, Grammatik und Rechtschreibung.
- Gliedere in sinnvolle Absätze; Markdown erlaubt.
- Bewahre den Ton und die Ich-Perspektive des Nutzers.

In deiner ersten Antwort:
1. Gib den strukturierten Textentwurf zurück.
2. Stelle 1-3 kurze, offene Reflexionsfragen, die dem Nutzer helfen
   könnten, den Eintrag zu vertiefen. Keine Vorgaben, keine Wertungen.

Bei Folgenachrichten: Aktualisiere den Entwurf basierend auf der neuen
Eingabe des Nutzers und stelle ggf. eine weitere Frage. Höre auf zu
fragen, wenn der Nutzer signalisiert, dass er fertig ist.
```

**`FINALIZE_SYSTEM_PROMPT`** (beim Speichern):

```
Fasse den bisherigen Dialog in einen finalen Tagebucheintrag zusammen.
Gib AUSSCHLIESSLICH JSON zurück, das folgendem Schema entspricht:

{
  "title": "<prägnanter Titel, max. 80 Zeichen>",
  "content": "<vollständiger Eintrag in Markdown, Ich-Perspektive, Ton bewahrt>",
  "tags": ["<3-7 Schlagwörter, kleingeschrieben, keine Duplikate>"],
  "entry_date": "<YYYY-MM-DD, Standardwert: heute>"
}

Verwende bevorzugt bereits existierende Tags, wenn sinnvoll: {EXISTING_TAGS}.
Wenn der Nutzer ein explizites Datum erwähnt hat, nutze es.
Erfinde keine Inhalte, die im Dialog nicht vorkamen.
```

`{EXISTING_TAGS}` wird serverseitig durch die aktuelle Tag-Liste ersetzt.

## 8. Sicherheit

- HTTPS obligatorisch für Nicht-Localhost-Deployments (Caddy + Let's Encrypt).
- Session-Cookies: `HttpOnly`, `Secure`, `SameSite=Strict`.
- Passwort: argon2id-Hash in `settings.password_hash`.
- Optional TOTP-2FA (`pyotp`). QR-Code-Setup in Settings-UI.
- DB: SQLCipher-Volltextverschlüsselung. Key aus `DB_ENCRYPTION_KEY` (64 Hex, in `.env`).
- API-Keys in DB zusätzlich mit separatem Key aus `SECRET_KEY_WRAP` (ENV) verschlüsselt, damit ein Leak der DB-Datei ohne ENV nicht ausreicht.
- CSRF-Double-Submit-Token für POST/PUT/DELETE.
- Rate-Limits (s. 5.2).
- Audio-Dateien werden nach Transkription sofort gelöscht.
- Repo-Schutz: `.gitignore` schließt `.env`, `data/`, `*.db`, Audio-Dateien aus.

## 9. Konfiguration

`deploy/.env.example` wird mitgeliefert; `deploy/.env` gehört nicht ins Repo.

```
# Pflicht
DOMAIN=journal.example.com
APP_PASSWORD=CHANGE_ME
DB_ENCRYPTION_KEY=CHANGE_ME_64_HEX
SESSION_SECRET=CHANGE_ME_64_HEX
SECRET_KEY_WRAP=CHANGE_ME_64_HEX

# Sessions
SESSION_IDLE_MINUTES=10
SESSION_ABSOLUTE_HOURS=12

# STT, Chat, Embeddings (Phase 2), TTS (Phase 3)
STT_BASE_URL=https://api.openai.com/v1
STT_API_KEY=
STT_MODEL=whisper-1

CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=
CHAT_MODEL=gpt-4o-mini

EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=
EMBED_MODEL=text-embedding-3-small

TTS_BASE_URL=https://api.openai.com/v1
TTS_API_KEY=
TTS_MODEL=tts-1

MAX_UPLOAD_MB=25
```

## 10. Kompatibilitätsmatrix (Dokumentation)

Details in `docs/endpoint-compatibility.md`.

| Fähigkeit | OpenAI Cloud | Ollama | Separater Server |
|---|---|---|---|
| Chat | ✅ | ✅ (`/v1/chat/completions`) | LocalAI, vLLM, llama.cpp |
| Embeddings | ✅ | ✅ (`/v1/embeddings`) | LocalAI, Infinity |
| STT | ✅ | ❌ | faster-whisper-server, whisper.cpp server |
| TTS | ✅ | ❌ | openedai-speech, Piper, Kokoro-FASTAPI, Orpheus-FASTAPI |

Fully-lokaler Betrieb benötigt daher drei Endpoints: Ollama (Chat+Embeddings), STT-Server, TTS-Server.

## 11. Hardware-Profile (Dokumentation)

Details in `docs/hardware-profiles.md`.

**Minimal (RTX 3060 12 GB, 32 GB RAM):**
Chat Qwen 2.5 7B Q4 (Ollama) · Embeddings bge-m3 (Ollama) · STT faster-whisper `medium` auf CPU · TTS Piper.

**Komfort (RTX 4060 Ti 16 GB / M3 Pro):**
Chat Mistral Nemo 12B Q4 · Embeddings bge-m3 · STT Whisper `large-v3` int8 auf GPU · TTS Kokoro.

Ollama entlädt ungenutzte Modelle aus VRAM (`OLLAMA_KEEP_ALIVE`). Self-Hosting wird als Power-User-Pfad dokumentiert, nicht als Default-Installation.

## 12. Tests

- **Backend (pytest):** Unit-Tests für Services, Integration-Tests für alle Routes mit `respx`-gemockten externen Endpoints. Coverage-Ziel: ≥ 80 %.
- **Frontend (Vitest):** Komponententests für `TextOrVoiceInput`, Chat-Logik, Session-Store.
- **E2E (Playwright):** kritische Flows — Login, Eintrag erstellen (Text-only, da MediaRecorder in Headless schwierig ist), Eintrag editieren, Tag-Filter, Session-Ablauf.
- **CI (GitHub Actions):** `backend-test.yml`, `frontend-test.yml`, `build.yml` (Image-Build zur Validierung, kein Push).

## 13. Out-of-Scope für Phase 1

Ausgeschlossen (separate Specs für spätere Phasen):

- Embeddings-Pipeline und semantische Suche via `sqlite-vec` (Phase 2).
- TTS-Vorlesen eines Eintrags mit Audio-Player (Phase 3).
- Datenexport (JSON, Markdown).
- Stimmungsanalyse, Timeline-Visualisierung, Statistiken.
- Benachrichtigungen / tägliche Erinnerungen.

## 14. Offene Punkte

Keine blockierenden — der Plan kann geschrieben werden. Während der Implementierung zu verifizieren:

- SQLCipher-Python-Binding-Wahl (`pysqlcipher3` vs. `sqlcipher3-wheels`); auf Alpine eventuell anders als auf Debian-Base.
- Fallback, falls der Chat-Endpoint kein echtes JSON-Mode kann (kein `response_format`): dann Prompt-Only-JSON mit striktem Validator.
- PWA: Service-Worker darf `/api/*` nicht cachen, um Cookie-Sessions nicht zu brechen.
