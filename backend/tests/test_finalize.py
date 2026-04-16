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


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.merge(Tag(name="reise"))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.query(Tag).delete()
        db.commit()


def _final_resp(title: str = "Test", tags=None):
    if tags is None:
        tags = ["reise"]
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps({
                "title": title, "content": "ok", "tags": tags,
                "entry_date": "2026-04-14",
            })},
        }],
    }


def test_finalize_returns_structured_json():
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=_final_resp())
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/chat/finalize",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Test"
    assert data["tags"] == ["reise"]


def test_finalize_falls_back_when_json_mode_rejected():
    """Simulate a server that rejects response_format with 400."""
    sid = create_session()
    call_count = {"n": 0}

    def _handler(request):
        call_count["n"] += 1
        body = request.content.decode()
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return httpx.Response(200, json=_final_resp(title="Fallback"))

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=_handler)
        with TestClient(app) as c:
            r = c.post(
                "/api/chat/finalize",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    assert r.json()["title"] == "Fallback"
    assert call_count["n"] >= 2


def test_finalize_sets_default_date_when_missing():
    from datetime import date
    sid = create_session()
    response_without_date = {
        "id": "cmpl-2",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps({
                "title": "NoDate", "content": "x", "tags": []
            })},
        }],
    }
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=response_without_date))
        with TestClient(app) as c:
            r = c.post(
                "/api/chat/finalize",
                json={"messages": [{"role": "user", "content": "x"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    assert r.json()["entry_date"] == date.today().isoformat()
