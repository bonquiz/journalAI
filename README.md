# journalAI

Self-hosted, open-source, single-user voice/text journal with LLM-assisted structuring.
OpenAI-compatible endpoints for STT, chat, embeddings, TTS — run fully in the cloud,
fully locally, or mix-and-match.

## Features

- **Voice or text input** — dictate or type; LLM structures raw input into a tidy entry
- **Chat-guided finalization** — refine the draft in a chat dialog before saving
- **Tag management** — rename, merge, delete from a dedicated `/tags` page
- **Semantic search** — ask natural-language questions over your journal
  (`"hab ich mal über einen Regenbogen-Traum geschrieben?"`); LLM re-ranks results
  with a short reason per match
- **Read-aloud (TTS)** — play back any entry or chat reply
- **SQLCipher-encrypted storage** — the entire journal DB is at-rest encrypted
- **Single-user, self-hosted** — Docker Compose with automatic HTTPS via Caddy

## Quick Start

```bash
cp deploy/.env.example deploy/.env
# Edit deploy/.env — set DOMAIN, APP_PASSWORD, and three 64-hex secrets.
# For endpoints: fill OPENAI_API_KEY if you want to use OpenAI for everything,
# or set per-capability URL/KEY/MODEL lines for self-hosted / mixed setups.
docker compose -f deploy/docker-compose.yml up -d
```

See:
- `docs/self-hosting.md` — full setup guide
- `docs/endpoint-compatibility.md` — which AI providers/servers work
- `docs/hardware-profiles.md` — recommended hardware for local-only setups

## E2E-Tests live ausführen

Die Playwright-Specs unter `frontend/tests/e2e/` sind standardmäßig per `test.skip(!E2E_LIVE)`
deaktiviert, weil sie echte Requests an OpenAI-kompatible Endpoints senden (Kosten, Latenz).

**Voraussetzungen:**
- Backend und Frontend laufen lokal (`docker compose -f deploy/docker-compose.yml up -d`).
- Ein Seed-User existiert (`APP_PASSWORD` aus `deploy/.env`).
- Ein OpenAI-kompatibler Endpoint ist erreichbar.

**Lauf:**

```bash
cd frontend
E2E_LIVE=1 \
  OPENAI_API_KEY=sk-... \
  OPENAI_BASE_URL=https://api.openai.com/v1 \
  npx playwright test
```

**Hinweis:** Live-Läufe erzeugen echte Kosten/Requests gegen den konfigurierten Provider.
Für die normale lokale Entwicklung genügt der Default-Skip; CI führt ebenfalls nur die
gated Specs ohne `E2E_LIVE` aus.

## Privacy

No journal data, audio, or secrets are ever committed to this repository.
Your data lives in the `./data/` Docker volume. Audio files are discarded
immediately after transcription.

## Lokaler LLM-Stack (optional, privacy-first)

journalAI läuft standardmäßig gegen OpenAI-kompatible Endpoints (jeder Provider). Für kompletten Lokal-Betrieb ohne Cloud existiert ein offizielles Compose-Profil mit Ollama (Chat + Embed), speaches (STT) und Kokoro-FastAPI (TTS).

- **Lokal auf eigener Hardware:** [`docs/self-hosting/local-llm.md`](docs/self-hosting/local-llm.md)
- **Ohne geeignete Hardware → Hetzner Cloud:** [`docs/self-hosting/hetzner.md`](docs/self-hosting/hetzner.md)

### Performance-Referenz

| Tier | Chat (chars/s) | STT (RTF, lower=faster) | Embed (entries/s) | TTS (RTF, lower=faster) |
|---|---|---|---|---|
| Minimal (CPX41, CPU) | `TBD` | `TBD` | `TBD` | `TBD` |
| Recommended (GEX44, RTX 6000 Ada) | `TBD` | `TBD` | `TBD` | `TBD` |

Detailreports: [`docs/benchmarks/`](docs/benchmarks/). Benchmarks stammen von einem realen Hetzner-Testlauf, nicht aus Herstellerangaben.
