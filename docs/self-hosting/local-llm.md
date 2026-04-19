# Local LLM stack

🇩🇪 [Deutsche Version](local-llm.de.md)

journalAI can run fully locally, without OpenAI or any other cloud provider. All four capabilities (Chat, Embeddings, STT, TTS) run as Docker containers next to the backend and frontend.

## Requirements

| | Minimal (CPU) | Recommended (GPU) |
|---|---|---|
| CPU | 8 cores (dedicated) | 4 cores |
| RAM | 16 GB | 16 GB |
| GPU | — | NVIDIA, ≥8 GB VRAM, driver ≥535, nvidia-container-toolkit |
| Disk | 20 GB (models) | 50 GB (larger models) |

## Steps

1. **Create `.env.local-llm`:**
   ```bash
   cp deploy/.env.local-llm.example deploy/.env.local-llm
   ```
   Then uncomment the tier block you want (Minimal or Recommended).

2. **Start the stack:**
   ```bash
   # Minimal (CPU)
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
     --env-file deploy/.env --env-file deploy/.env.local-llm up -d

   # Recommended (GPU)
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
     -f deploy/docker-compose.local-llm.gpu.yml \
     --env-file deploy/.env --env-file deploy/.env.local-llm up -d
   ```

3. **First boot takes 5–20 min:** the `ollama-init` one-shot container pulls the Chat and Embed models; speaches and the TTS service load their models on first request. Watch progress:
   ```bash
   docker compose logs -f ollama-init
   ```

4. **Log in:** Backend auto-exposes the ENV values via `/api/settings`; the UI shows an `aus ENV: …` hint under empty fields.

5. **Smoke-test:** record a voice entry or try semantic search. If a request returns 502, check container logs — the most common cause is a model that hasn't finished downloading yet.

## Switching the German TTS voice

The default TTS service is [openedai-speech](https://github.com/matatonic/openedai-speech), a wrapper for [Piper](https://github.com/rhasspy/piper). The included `thorsten` voice (`de_DE-thorsten-high`) gives native-sounding German. For a different voice, see openedai-speech's docs for adding Piper voices via `voice_to_speaker.yaml`.

Known gotcha on fresh deploys: the Whisper STT model needs a one-time pull:

```bash
docker exec journalai-speaches-1 \
  curl -s -X POST http://localhost:8000/v1/models/Systran/faster-whisper-base
```

And the Piper German voice files need to be downloaded once into the kokoro container under `/app/voices/`. Automating this is tracked as U9 in the roadmap.

## FAQ

- **Can I mix capabilities?** Yes — enter different endpoints/models per capability in the Settings UI. The DB overrides ENV, so any UI change takes effect immediately.
- **How do I swap the Chat model?** Edit `.env.local-llm`, then `docker compose up -d ollama-init` to pull the new model (already-pulled ones are skipped).
- **Why is Minimal tier so slow?** See [`docs/benchmarks/`](../benchmarks/) — CPU-only chat with 7B models is inherently slow. Smaller models (3B Q4) are noticeably faster but noticeably worse. Real daily use needs a GPU.
- **Image versions:** pinned in the compose file. Verify with `docker manifest inspect <image>:<tag>` if you want to bump.
