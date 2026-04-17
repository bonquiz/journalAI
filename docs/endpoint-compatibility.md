# Endpoint Compatibility

journalAI speaks the OpenAI-compatible HTTP API for all four AI capabilities: STT (speech-to-text),
Chat (LLM completions), Embeddings, and TTS (text-to-speech). Any server that implements these
endpoints can be used in place of OpenAI's cloud API — mix and match as needed.

## Compatibility Matrix

| Capability | OpenAI Cloud | Ollama | Separate server |
|---|---|---|---|
| Chat | ✅ | ✅ `/v1/chat/completions` | LocalAI, vLLM, llama.cpp |
| Embeddings | ✅ | ✅ `/v1/embeddings` | LocalAI, Infinity |
| STT | ✅ (whisper-1) | ❌ | faster-whisper-server, whisper.cpp server |
| TTS | ✅ (tts-1) | ❌ | openedai-speech, Piper (via proxy), Kokoro-FASTAPI, Orpheus-FASTAPI |

> **Note:** Ollama does not natively serve `/audio/transcriptions` or `/audio/speech`.
> For local STT and TTS you need separate servers (see table above).

## Resolution Chain

For each capability the backend resolves `(base_url, api_key, model)` via this chain:

1. **DB override** — whatever you set in `/settings` (per-capability URL / key / model).
2. **ENV default** — from `deploy/.env` (`STT_BASE_URL`, `STT_API_KEY`, `STT_MODEL`, etc.).
3. **Shared `OPENAI_API_KEY`** — if the capability's *key* is empty AND its base URL
   points at `api.openai.com`. Lets you fill in just one key for an all-OpenAI setup.
4. **OpenAI default model** — if the capability's *model* is empty AND its base URL
   points at `api.openai.com`. Built-in defaults: STT=`whisper-1`, Chat=`gpt-4o-mini`,
   Embed=`text-embedding-3-small`, TTS=`tts-1`. Keeps an all-OpenAI setup working even
   when the model fields are left blank.

For non-OpenAI base URLs there is **no model fallback** — third-party servers expose
arbitrary model identifiers, so you must set `{CAP}_MODEL` (or the DB override) explicitly.

## Configuration Examples

### Minimum (all-OpenAI)

```env
OPENAI_API_KEY=sk-...
# Everything else can stay blank — defaults resolve to api.openai.com with
# whisper-1 / gpt-4o-mini / text-embedding-3-small / tts-1.
```

### all-OpenAI (explicit)

```env
STT_BASE_URL=https://api.openai.com/v1
STT_API_KEY=$OPENAI_API_KEY
STT_MODEL=whisper-1

CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=$OPENAI_API_KEY
CHAT_MODEL=gpt-4o

EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=$OPENAI_API_KEY
EMBED_MODEL=text-embedding-3-small

TTS_BASE_URL=https://api.openai.com/v1
TTS_API_KEY=$OPENAI_API_KEY
TTS_MODEL=tts-1
```

### all-local

```env
STT_BASE_URL=http://whisper:8000/v1
STT_API_KEY=ignored
STT_MODEL=medium

CHAT_BASE_URL=http://ollama:11434/v1
CHAT_API_KEY=ignored
CHAT_MODEL=qwen2.5:7b-instruct-q4_K_M

EMBED_BASE_URL=http://ollama:11434/v1
EMBED_API_KEY=ignored
EMBED_MODEL=bge-m3

TTS_BASE_URL=http://tts:8001/v1
TTS_API_KEY=ignored
TTS_MODEL=en_US-lessac-medium
```

### hybrid

```env
# Chat and Embeddings via local Ollama
CHAT_BASE_URL=http://ollama:11434/v1
CHAT_API_KEY=ignored
CHAT_MODEL=qwen2.5:7b-instruct-q4_K_M

EMBED_BASE_URL=http://ollama:11434/v1
EMBED_API_KEY=ignored
EMBED_MODEL=bge-m3

# STT and TTS via OpenAI cloud
STT_BASE_URL=https://api.openai.com/v1
STT_API_KEY=$OPENAI_API_KEY
STT_MODEL=whisper-1

TTS_BASE_URL=https://api.openai.com/v1
TTS_API_KEY=$OPENAI_API_KEY
TTS_MODEL=tts-1
```
