"""Per-capability OpenAI-compatible client factory.

Each capability (stt, chat, embed, tts) gets an independent OpenAI() instance
with its own base_url / api_key / model, read from the AppSettings row
(DB override) with ENV defaults as fallback.

If no capability-specific key is set (neither in DB nor ENV) AND the effective
base_url points at api.openai.com, `OPENAI_API_KEY` is used as a shared fallback.
"""
from typing import Literal

from openai import OpenAI

from app.config import settings as env
from app.crypto import unwrap_secret
from app.db import SessionLocal
from app.models.settings import AppSettings

Capability = Literal["stt", "chat", "embed", "tts"]

_DEFAULTS: dict[str, tuple[str, str, str]] = {
    "stt":   (env.stt_base_url,   env.stt_api_key,   env.stt_model),
    "chat":  (env.chat_base_url,  env.chat_api_key,  env.chat_model),
    "embed": (env.embed_base_url, env.embed_api_key, env.embed_model),
    "tts":   (env.tts_base_url,   env.tts_api_key,   env.tts_model),
}


def _db_override(cap: str) -> tuple[str | None, str | None, str | None]:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None:
            return (None, None, None)
        wrapped = getattr(s, f"{cap}_api_key_wrapped", None)
        return (
            getattr(s, f"{cap}_base_url", None),
            unwrap_secret(wrapped) if wrapped else None,
            getattr(s, f"{cap}_model", None),
        )


def get_client(cap: Capability) -> tuple[OpenAI, str]:
    if cap not in _DEFAULTS:
        raise ValueError(f"unknown capability: {cap}")
    db_url, db_key, db_model = _db_override(cap)
    d_url, d_key, d_model = _DEFAULTS[cap]

    base_url = db_url or d_url
    model = db_model or d_model

    # Resolution order for the key:
    #   1. DB override (capability-specific)
    #   2. ENV default  (capability-specific, e.g. STT_API_KEY)
    #   3. OPENAI_API_KEY — but only if base_url points at OpenAI's API
    #   4. "unused"      — local servers accept any non-empty string
    api_key = db_key or d_key
    if not api_key and "api.openai.com" in (base_url or "") and env.openai_api_key:
        api_key = env.openai_api_key
    if not api_key:
        api_key = "unused"

    return OpenAI(base_url=base_url, api_key=api_key), model
