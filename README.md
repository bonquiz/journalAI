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

## Privacy

No journal data, audio, or secrets are ever committed to this repository.
Your data lives in the `./data/` Docker volume. Audio files are discarded
immediately after transcription.
