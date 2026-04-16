import httpx
import pytest
import respx

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.settings import AppSettings
from app.services.tts import synthesize


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(
            id=1,
            password_hash=hash_password("pw"),
            tts_voice="nova",
            tts_speed=1.1,
        ))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def test_synthesize_short_text_single_call():
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        route = mock.post("/audio/speech").mock(
            return_value=httpx.Response(200, content=b"MP3FAKE1", headers={"Content-Type": "audio/mpeg"})
        )
        out = synthesize("Hallo Welt.")
    assert out == b"MP3FAKE1"
    assert route.called
    assert route.call_count == 1


def test_synthesize_long_text_chunks_and_concats():
    sentences = ("Dies ist ein langer Satz. " * 300)
    calls = {"n": 0}

    def _handler(request):
        calls["n"] += 1
        return httpx.Response(
            200,
            content=f"CHUNK{calls['n']}".encode(),
            headers={"Content-Type": "audio/mpeg"},
        )

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(side_effect=_handler)
        out = synthesize(sentences)

    assert calls["n"] >= 2
    assert out.startswith(b"CHUNK1")
    expected_tail = b"".join(f"CHUNK{i}".encode() for i in range(1, calls["n"] + 1))
    assert out == expected_tail


def test_synthesize_falls_back_without_speed_on_400():
    call_log: list[dict] = []

    def _handler(request):
        import json as _json
        body = _json.loads(request.content)
        call_log.append(body)
        if "speed" in body:
            return httpx.Response(
                400,
                json={"error": {"message": "speed parameter not supported"}},
            )
        return httpx.Response(200, content=b"OK", headers={"Content-Type": "audio/mpeg"})

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(side_effect=_handler)
        out = synthesize("Kurz.", speed=1.5)

    assert out == b"OK"
    assert len(call_log) == 2
    assert "speed" in call_log[0]
    assert "speed" not in call_log[1]


def test_synthesize_uses_db_voice_when_no_override():
    captured: list[dict] = []

    def _handler(request):
        import json as _json
        captured.append(_json.loads(request.content))
        return httpx.Response(200, content=b"X", headers={"Content-Type": "audio/mpeg"})

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(side_effect=_handler)
        synthesize("Hallo.")

    assert captured[0]["voice"] == "nova"


def test_synthesize_explicit_voice_overrides_db():
    captured: list[dict] = []

    def _handler(request):
        import json as _json
        captured.append(_json.loads(request.content))
        return httpx.Response(200, content=b"X", headers={"Content-Type": "audio/mpeg"})

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(side_effect=_handler)
        synthesize("Hallo.", voice="alloy")

    assert captured[0]["voice"] == "alloy"


def test_synthesize_raises_on_non_400_http_error():
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(return_value=httpx.Response(500, json={"error": "boom"}))
        with pytest.raises(Exception):
            synthesize("Hallo.")


def test_chunker_splits_after_german_closing_quote():
    """The splitter must handle „...!" Dann ... correctly."""
    from app.services.tts import _split_into_chunks
    text = (
        "\u201eHallo!\u201c geht es los. Dies ist der zweite Satz. "
        "Dies ist ein weiterer Satz mit \u00bbfranз\u00f6sischen\u00ab Anf\u00fchrungszeichen. "
        "Noch ein Satz."
    )
    chunks = _split_into_chunks(text, max_chars=60)
    joined = " ".join(chunks)
    assert "\u201eHallo!\u201c" in joined
    assert all(c.strip() == c for c in chunks)
    assert len(chunks) >= 2
