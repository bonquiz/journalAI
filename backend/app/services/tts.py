"""Text-to-speech synthesis.

Uses the OpenAI-compatible /v1/audio/speech endpoint via `get_client("tts")`.
Long text is split on sentence boundaries into chunks <=3800 chars (below the
typical 4096 provider limit) and the resulting MP3 byte streams are
concatenated directly.

MP3 byte concatenation works reliably with OpenAI `tts-1` (validated in this
project) because each response is a single CBR MP3 stream without leading ID3
tags. Other OpenAI-compatible providers (openedai-speech, Kokoro-FASTAPI) have
been observed to work in practice but are NOT formally validated here. If a
provider emits VBR with Xing/Info headers, concatenation may produce incorrect
duration metadata — the audio still plays but the timeline may skip. Escape
hatch: swap the `b"".join()` for pydub-based stitching in a follow-up.

If the provider rejects the `speed` parameter (400/422 with a matching error
message), the call is retried once without `speed`. This mirrors the
JSON-mode fallback used in chat finalize.
"""
from __future__ import annotations

import re

from app.config import settings as env
from app.db import SessionLocal
from app.models.settings import AppSettings
from app.services.llm_client import get_client

_MAX_CHUNK = 3800
_DEFAULT_VOICE = "alloy"
_DEFAULT_SPEED = 1.0


def _resolved_voice_and_speed(voice: str | None, speed: float | None) -> tuple[str, float]:
    """Resolve voice/speed. Chain: call-param -> DB -> ENV (TTS_VOICE / TTS_SPEED) -> hardcoded default."""
    if voice is None or speed is None:
        with SessionLocal() as db:
            s = db.get(AppSettings, 1)
            db_voice = s.tts_voice if s else None
            db_speed = s.tts_speed if s else None
    else:
        db_voice = None
        db_speed = None
    env_voice = getattr(env, "tts_voice", "") or None
    env_speed = getattr(env, "tts_speed", None)
    return (
        voice or db_voice or env_voice or _DEFAULT_VOICE,
        speed if speed is not None
        else (db_speed if db_speed is not None
              else (env_speed if env_speed is not None else _DEFAULT_SPEED)),
    )


def _split_into_chunks(text: str, max_chars: int = _MAX_CHUNK) -> list[str]:
    """Greedy-pack sentences into buckets of <= max_chars.

    Splits on sentence terminators (.!?) followed by optional closing quote
    (straight or typographic, including German \u201e...\u201c, French/German \u00bb...\u00ab,
    single quotes), then whitespace. Also splits on double newlines.
    """
    if len(text) <= max_chars:
        return [text]

    pieces = re.split(
        r'(?<=[.!?]["\'\u00bb\u201c\u2019\u00ab])\s+|(?<=[.!?])\s+|\n{2,}',
        text.strip(),
    )

    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) > max_chars:
            words = piece.split()
            inner = ""
            for w in words:
                if len(inner) + len(w) + 1 > max_chars:
                    chunks.append(inner.strip())
                    inner = w
                else:
                    inner = f"{inner} {w}".strip()
            if inner:
                if buf:
                    chunks.append(buf.strip())
                    buf = ""
                chunks.append(inner)
            continue

        candidate = f"{buf} {piece}".strip() if buf else piece
        if len(candidate) > max_chars:
            chunks.append(buf.strip())
            buf = piece
        else:
            buf = candidate
    if buf:
        chunks.append(buf.strip())
    return chunks


def _call_once(
    client,
    model: str,
    voice: str,
    speed: float,
    text: str,
    include_speed: bool,
) -> bytes:
    kwargs: dict = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "mp3",
    }
    if include_speed:
        kwargs["speed"] = speed
    resp = client.audio.speech.create(**kwargs)
    if hasattr(resp, "read"):
        return resp.read()
    return resp.content  # type: ignore[no-any-return]


def synthesize(
    text: str,
    voice: str | None = None,
    speed: float | None = None,
) -> bytes:
    """Return MP3 bytes for the full text, chunked + concatenated if needed."""
    client, model = get_client("tts")
    resolved_voice, resolved_speed = _resolved_voice_and_speed(voice, speed)

    chunks = _split_into_chunks(text)
    out = bytearray()

    include_speed = True
    try:
        first = _call_once(client, model, resolved_voice, resolved_speed, chunks[0], include_speed=True)
        out.extend(first)
    except Exception as e:
        msg = str(e).lower()
        if "speed" in msg and ("400" in msg or "422" in msg or "unsupported" in msg or "not supported" in msg):
            include_speed = False
            first = _call_once(client, model, resolved_voice, resolved_speed, chunks[0], include_speed=False)
            out.extend(first)
        else:
            raise

    for chunk in chunks[1:]:
        out.extend(
            _call_once(client, model, resolved_voice, resolved_speed, chunk, include_speed=include_speed)
        )

    return bytes(out)
