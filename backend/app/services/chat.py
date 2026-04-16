"""Chat streaming service. Uses OpenAI-compatible /v1/chat/completions with
stream=True. System prompt is DB-configurable via AppSettings.system_prompt;
falls back to the STRUCTURE_SYSTEM_PROMPT default.
"""
import json
from collections.abc import Iterator
from datetime import date

from app.db import SessionLocal
from app.models.settings import AppSettings
from app.models.tag import Tag
from app.services.llm_client import get_client
from app.services.prompts import FINALIZE_SYSTEM_PROMPT, STRUCTURE_SYSTEM_PROMPT


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


def _existing_tags() -> list[str]:
    with SessionLocal() as db:
        return [t.name for t in db.query(Tag).all()]


def finalize(messages: list[dict]) -> dict:
    """Run the finalize step with JSON-mode + graceful fallback.

    Some OpenAI-compatible servers (Ollama older builds) reject `response_format`
    with 400/422. We catch that and retry without JSON-mode, using a stricter
    system prompt. If parsing still fails, a second retry with an even stricter
    hint is attempted. If that fails, the JSONDecodeError propagates to the caller.
    """
    client, model = get_client("chat")
    system = FINALIZE_SYSTEM_PROMPT.format(existing_tags=_existing_tags())

    def _call(use_json_mode: bool, extra_hint: str = "") -> str:
        msgs = [{"role": "system", "content": system + extra_hint}] + messages
        kwargs: dict = {"model": model, "messages": msgs}
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or "{}"

    # Try JSON-mode first; fall back on 400/422 or mentions of response_format.
    try:
        raw = _call(use_json_mode=True)
    except Exception as e:
        msg = str(e).lower()
        if "400" in msg or "422" in msg or "response_format" in msg or "unsupported" in msg:
            raw = _call(
                use_json_mode=False,
                extra_hint="\n\nAntworte AUSSCHLIESSLICH mit validem JSON. Kein Fließtext.",
            )
        else:
            raise

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raw2 = _call(
            use_json_mode=False,
            extra_hint="\n\nDeine Antwort MUSS exakt ein JSON-Objekt sein. Nichts anderes.",
        )
        obj = json.loads(raw2)  # if this fails, propagate → 500

    obj.setdefault("entry_date", date.today().isoformat())
    return obj
