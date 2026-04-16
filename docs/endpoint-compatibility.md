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

## Configuration Examples

### all-OpenAI

```env
STT_BASE_URL=https://api.openai.com/v1
STT_API_KEY=$OPENAI_API_KEY
STT_MODEL=whisper-1

CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=$OPENAI_API_KEY
CHAT_MODEL=gpt-4o

EMBEDDINGS_BASE_URL=https://api.openai.com/v1
EMBEDDINGS_API_KEY=$OPENAI_API_KEY
EMBEDDINGS_MODEL=text-embedding-3-small

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

EMBEDDINGS_BASE_URL=http://ollama:11434/v1
EMBEDDINGS_API_KEY=ignored
EMBEDDINGS_MODEL=bge-m3

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

EMBEDDINGS_BASE_URL=http://ollama:11434/v1
EMBEDDINGS_API_KEY=ignored
EMBEDDINGS_MODEL=bge-m3

# STT and TTS via OpenAI cloud
STT_BASE_URL=https://api.openai.com/v1
STT_API_KEY=$OPENAI_API_KEY
STT_MODEL=whisper-1

TTS_BASE_URL=https://api.openai.com/v1
TTS_API_KEY=$OPENAI_API_KEY
TTS_MODEL=tts-1
```
