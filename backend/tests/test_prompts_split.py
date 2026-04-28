"""Tests für split coach/summary prompts (Spec 2026-04-28)."""
import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings
from app.models.tag import Tag
from app.services.chat import _coach_prompt, _summary_prompt
from app.services.prompts import (
    COACH_PRESETS,
    DEFAULT_COACH_PROMPT,
    DEFAULT_COACH_PRESET_KEY,
    DEFAULT_SUMMARY_PROMPT,
    SUMMARY_JSON_SCHEMA_SUFFIX,
)


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.query(Tag).delete()
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.query(Tag).delete()
        db.commit()


def _set(field: str, value):
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        setattr(s, field, value)
        db.commit()


def test_default_coach_prompt_used_when_db_empty():
    _set("coach_prompt", None)
    assert _coach_prompt(None) == DEFAULT_COACH_PROMPT


def test_custom_coach_prompt_used_when_set():
    _set("coach_prompt", "Du bist Yoda.")
    try:
        assert _coach_prompt(None) == "Du bist Yoda."
    finally:
        _set("coach_prompt", None)


def test_chat_request_override_wins_over_db():
    _set("coach_prompt", "DB-Wert")
    try:
        assert _coach_prompt("Override-Wert") == "Override-Wert"
    finally:
        _set("coach_prompt", None)


def test_default_summary_prompt_uses_default_plus_suffix():
    _set("summary_prompt", None)
    out = _summary_prompt()
    assert out.startswith(DEFAULT_SUMMARY_PROMPT)
    assert SUMMARY_JSON_SCHEMA_SUFFIX in out


def test_custom_summary_prompt_uses_user_text_plus_suffix():
    _set("summary_prompt", "Mein eigener Stil-Prompt.")
    try:
        out = _summary_prompt()
        assert out.startswith("Mein eigener Stil-Prompt.")
        assert SUMMARY_JSON_SCHEMA_SUFFIX in out
    finally:
        _set("summary_prompt", None)


def test_summary_prompt_format_substitutes_existing_tags():
    _set("summary_prompt", None)
    raw = _summary_prompt()
    formatted = raw.format(existing_tags=["reise", "arbeit"])
    assert "['reise', 'arbeit']" in formatted
    assert "{existing_tags}" not in formatted


def test_coach_presets_have_four_entries():
    assert set(COACH_PRESETS.keys()) == {"therapist", "coach", "stoic", "spiritual"}
    assert DEFAULT_COACH_PRESET_KEY == "therapist"


def test_settings_get_returns_coach_presets():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/settings", cookies={"session": sid, "csrf": "t"})
    assert r.status_code == 200
    data = r.json()
    assert {p["key"] for p in data["coach_presets"]} == {
        "therapist", "coach", "stoic", "spiritual",
    }
    assert data["default_coach_preset_key"] == "therapist"
    therapist = next(p for p in data["coach_presets"] if p["key"] == "therapist")
    assert "Therapeut" == therapist["label"]
    assert therapist["text"].startswith("Du bist ein einfühlsamer")


def test_settings_patch_empty_string_resets_coach_prompt_to_null():
    sid = create_session()
    _set("coach_prompt", "Mein eigener Prompt")
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"coach_prompt": ""},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).coach_prompt is None


def test_settings_patch_whitespace_only_resets_summary_prompt_to_null():
    sid = create_session()
    _set("summary_prompt", "X")
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"summary_prompt": "   \n   "},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).summary_prompt is None


def test_settings_patch_persists_non_empty_prompts():
    sid = create_session()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"coach_prompt": "Custom-Coach", "summary_prompt": "Custom-Summary"},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 200
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert s.coach_prompt == "Custom-Coach"
        assert s.summary_prompt == "Custom-Summary"
    _set("coach_prompt", None)
    _set("summary_prompt", None)


def test_finalize_uses_summary_prompt_with_existing_tags():
    """End-to-End: /api/chat/finalize benutzt _summary_prompt() inkl. Tag-Substitution."""
    sid = create_session()
    with SessionLocal() as db:
        db.merge(Tag(name="reise"))
        db.commit()

    captured = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "model": "gpt-4o-mini",
            "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps({
                    "title": "T", "content": "C", "tags": ["reise"],
                    "entry_date": "2026-04-28",
                })},
            }],
        })

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=_capture)
        with TestClient(app) as c:
            r = c.post(
                "/api/chat/finalize",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    sys_content = captured["body"]["messages"][0]["content"]
    assert "['reise']" in sys_content
    assert "{existing_tags}" not in sys_content
    assert "JSON" in sys_content  # Suffix wirklich angehängt
