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
  OPENAI_API_KEY=<your-openai-key> \
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

journalAI läuft standardmäßig gegen OpenAI-kompatible Endpoints (jeder Provider). Für kompletten Lokal-Betrieb ohne Cloud existiert ein offizielles Compose-Profil mit Ollama (Chat + Embed), speaches (STT) und openedai-speech/Piper (TTS — dt. Stimme via `thorsten`).

- **Lokal auf eigener Hardware:** [`docs/self-hosting/local-llm.md`](docs/self-hosting/local-llm.md)
- **Ohne geeignete Hardware → Hetzner Cloud (CPU) oder RunPod (GPU):** [`docs/self-hosting/hetzner.md`](docs/self-hosting/hetzner.md)

### Performance-Referenz (gemessen 2026-04-19)

| Tier | Chat | STT (RTF) | Embed | TTS (RTF) | Kosten/h |
|---|---|---|---|---|---|
| Minimal (CPX42, CPU) — qwen2.5:3b | 94 chars/s (~15 tok/s) | 0.03 | 3.5/s (nomic) | 0.3 | ~0,04 € |
| Recommended (RTX 4090, GPU) — qwen2.5:7b | 639 chars/s (**158 tok/s**) | — | — | — | ~0,34 $ |

Hinweis: Minimal-Tier ist brauchbar für Evaluation, aber Chat-Qualität mit qwen2.5:3b ist spürbar unter ChatGPT-Niveau (Grammatikfehler, Wortwiederholungen). **Für echten Betrieb wird GPU-Tier mit qwen2.5:14b oder größer empfohlen.**

Detailreports: [`docs/benchmarks/`](docs/benchmarks/). Benchmarks stammen von realen Cloud-Testläufen (Hetzner Cloud + RunPod Community), nicht aus Herstellerangaben.
