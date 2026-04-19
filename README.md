# journalAI

**Self-hosted, privacy-first voice & text journal with LLM-assisted structuring.**
Dictate or type, let an LLM turn rough input into a structured entry, search it all
with natural language — and keep the data on your own server. Works with any
OpenAI-compatible API (the cloud or fully local).

🇩🇪 **[Deutsche Version → README.de.md](README.de.md)**

---

## Features

- 🎙️ **Voice or text** — dictate a memo or type directly
- 💬 **Chat-guided finalization** — refine a draft in a short dialog before saving
- 🏷️ **Tags** — rename, merge, delete from `/tags`
- 🔍 **Semantic search** — ask in natural language (*"did I ever write about a rainbow dream?"*); LLM re-ranks the hits with a short reason per match
- 🔊 **Read-aloud (TTS)** — play back any entry or chat reply
- 🔐 **At-rest encrypted** — full SQLCipher encryption of the journal DB
- 🏠 **Self-hosted** — Docker Compose + automatic HTTPS via Caddy

## Two deploy paths — pick one

### 🚀 Path A: "I just want it working" (OpenAI-only, ≈ 5 minutes)

You need: an OpenAI API key, a machine with Docker, and a domain (or localhost).

```bash
git clone https://github.com/bonquiz/journalAI.git
cd journalAI
./scripts/init-env.sh        # asks 3 questions, generates all secrets
docker compose -f deploy/docker-compose.yml up -d
```

`init-env.sh` asks for:
1. Domain (or `localhost`)
2. App password
3. Your OpenAI API key

It auto-generates the three 64-hex secrets (`DB_ENCRYPTION_KEY`, `SESSION_SECRET`, `SECRET_KEY_WRAP`) — you never have to touch them.

Open `https://<your-domain>` and log in with your app password. That's it.

### 🏠 Path B: Fully local, no cloud (≈ 30 minutes)

You need: A machine with either Apple Silicon / a consumer NVIDIA GPU (8+ GB VRAM recommended) OR a strong CPU (8+ cores) — plus ~50 GB disk for models.

```bash
git clone https://github.com/bonquiz/journalAI.git
cd journalAI
./scripts/init-env.sh        # choose option 3 at the LLM prompt

cp deploy/.env.local-llm.example deploy/.env.local-llm
# Edit .env.local-llm: uncomment the Minimal (CPU) or Recommended (GPU) block

# CPU:
docker compose \
  -f deploy/docker-compose.yml \
  -f deploy/docker-compose.local-llm.yml \
  --env-file deploy/.env --env-file deploy/.env.local-llm \
  up -d

# GPU: add -f deploy/docker-compose.local-llm.gpu.yml (requires nvidia-container-toolkit)
```

Full local-stack guide: **[`docs/self-hosting/local-llm.md`](docs/self-hosting/local-llm.md)**

Don't have the hardware? A temporary Hetzner Cloud server works for evaluation: **[`docs/self-hosting/hetzner.md`](docs/self-hosting/hetzner.md)** (≈ 0.04 € / hour).

### 🔀 Mix-and-match

Every capability (chat, embed, STT, TTS) has its own base URL / API key / model. You can, for example, run chat on a local Ollama while letting OpenAI do the Whisper STT. Configure in `/settings` after login or in `deploy/.env`.

## Minimum requirements

- **Path A (cloud):** Any Linux server, 1 vCPU, 1 GB RAM, Docker + Docker Compose v2.
- **Path B (local):** 8+ CPU cores or GPU ≥ 8 GB VRAM, 16 GB RAM, 50 GB disk. See [`docs/hardware-profiles.md`](docs/hardware-profiles.md) for specifics.

## Performance — honest numbers (measured 2026-04-19)

| Tier | Hardware | Chat | STT (RTF) | Embed | TTS (RTF) | ~ Cost/h |
|---|---|---|---|---|---|---|
| Minimal | Hetzner cpx42 (CPU) + qwen2.5:**3b** | 94 chars/s (~15 tok/s) | 0.03 | 3.5/s (nomic) | 0.3 | €0.04 |
| Recommended | RunPod RTX 4090 + qwen2.5:**7b** | **639 chars/s / 158 tok/s** | — | — | — | $0.34 |

⚠️ **Honesty note:** Minimal tier works, but qwen2.5:3b produces noticeable grammar errors and word-finding issues. For real daily use we recommend the GPU tier with qwen2.5:14b or larger (Hetzner Cloud has no GPU instances at time of writing — see the Hetzner guide for alternatives like RunPod, Lambda, Paperspace).

Detailed reports: [`docs/benchmarks/`](docs/benchmarks/).

## Documentation

- **[`docs/self-hosting.md`](docs/self-hosting.md)** — production deploy (DNS, backups, updates)
- **[`docs/self-hosting/local-llm.md`](docs/self-hosting/local-llm.md)** — full local-stack guide
- **[`docs/self-hosting/hetzner.md`](docs/self-hosting/hetzner.md)** — Hetzner Cloud bootstrap + Tailscale hardening
- **[`docs/endpoint-compatibility.md`](docs/endpoint-compatibility.md)** — which providers/servers work
- **[`docs/hardware-profiles.md`](docs/hardware-profiles.md)** — hardware recommendations for local setups

## E2E tests

Playwright specs under `frontend/tests/e2e/` are gated by `E2E_LIVE=1` because they make real LLM requests (cost + latency).

```bash
cd frontend
E2E_LIVE=1 \
  OPENAI_API_KEY=<your-openai-key> \
  OPENAI_BASE_URL=https://api.openai.com/v1 \
  npx playwright test
```

## Privacy

Nothing from your journal, audio, or secrets is committed to this repository. Data lives in the `./data/` Docker volume (SQLCipher-encrypted). Audio files are discarded immediately after transcription.

## License

MIT — see [`LICENSE`](LICENSE).

## Contributing

Issues and pull requests welcome at https://github.com/bonquiz/journalAI.
