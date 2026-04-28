import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), coach_prompt="SYS"))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def _sse_chunk(content: str, finish_reason: str | None = None) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
    }


def _sse_body(contents: list[str]) -> str:
    body = ""
    for i, text in enumerate(contents):
        finish = "stop" if i == len(contents) - 1 else None
        body += "data: " + json.dumps(_sse_chunk(text, finish)) + "\n\n"
    body += "data: [DONE]\n\n"
    return body


def test_chat_streams_tokens():
    sid = create_session()
    sse_body = _sse_body(["Hi", " there"])
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                text=sse_body,
                headers={"content-type": "text/event-stream"},
            )
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    assert "Hi" in r.text and "there" in r.text


def test_chat_stream_ends_with_done():
    sid = create_session()
    sse_body = _sse_body(["x"])
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                text=sse_body,
                headers={"content-type": "text/event-stream"},
            )
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "x"}]},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.text.rstrip().endswith("[DONE]")


def test_chat_requires_auth():
    with TestClient(app) as c:
        r = c.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "x"}]},
            cookies={"csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 401
