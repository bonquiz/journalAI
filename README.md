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
