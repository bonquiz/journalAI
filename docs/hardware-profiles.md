# Hardware Profiles

Self-hosting journalAI fully locally requires a consumer GPU or Apple Silicon machine.
If you use cloud endpoints (OpenAI or any hosted inference provider), there are no hardware
requirements beyond a small VPS or home server capable of running Docker.

## Minimal Setup — RTX 3060 12 GB + 32 GB RAM

| Capability | Model / Server | Notes |
|---|---|---|
| Chat | Qwen 2.5 7B Q4_K_M via Ollama | ~5 GB VRAM, 30–50 tok/s |
| Embeddings | `bge-m3` via Ollama | ~1.2 GB VRAM, strong multilingual incl. German |
| STT | `faster-whisper-server` with `medium` model on **CPU** | Frees GPU for LLM; ~20–30 s for 5 min of audio |
| TTS | Piper on CPU | <500 MB RAM, deterministic German voices |

**Important:** set `OLLAMA_KEEP_ALIVE=2m` so Ollama frees VRAM between calls. Without this,
the LLM and embedding model may both try to stay resident simultaneously and exhaust VRAM.

## Comfort Setup — RTX 4060 Ti 16 GB / Apple M3 Pro

| Capability | Model / Server | Notes |
|---|---|---|
| Chat | Mistral Nemo 12B Q4_K_M via Ollama | Good reasoning, fits in 16 GB VRAM |
| Embeddings | `bge-m3` via Ollama | Same as minimal |
| STT | `faster-whisper-server` with `large-v3` int8 on GPU | Noticeably higher accuracy |
| TTS | Kokoro-FASTAPI | Markedly more natural than Piper |

## Realism Note

Self-hosting is a power-user path. Setting up Docker + CUDA + three separate AI services
typically takes **4–8 hours** for users who are not already familiar with Docker networking
and GPU passthrough. Most users should **start with OpenAI endpoints** and gradually migrate
individual components locally as they get comfortable with the stack.
