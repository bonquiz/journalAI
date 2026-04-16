"""Chat streaming service. Uses OpenAI-compatible /v1/chat/completions with
stream=True. System prompt is DB-configurable via AppSettings.system_prompt;
falls back to the STRUCTURE_SYSTEM_PROMPT default.
"""
from collections.abc import Iterator

from app.db import SessionLocal
from app.models.settings import AppSettings
from app.services.llm_client import get_client
from app.services.prompts import STRUCTURE_SYSTEM_PROMPT


def _system_prompt(override: str | None) -> str:
    if override:
        return override
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        return s.system_prompt if (s and s.system_prompt) else STRUCTURE_SYSTEM_PROMPT


def stream_chat(
    messages: list[dict], system_prompt_override: str | None = None
) -> Iterator[str]:
    client, model = get_client("chat")
    sys_msg = {"role": "system", "content": _system_prompt(system_prompt_override)}
    stream = client.chat.completions.create(
        model=model, messages=[sys_msg] + messages, stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta
