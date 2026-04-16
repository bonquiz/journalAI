import pytest
from app.crypto import wrap_secret, unwrap_secret


def test_roundtrip():
    token = wrap_secret("sk-abcdef")
    assert token != "sk-abcdef"
    assert unwrap_secret(token) == "sk-abcdef"


def test_empty_returns_empty():
    assert wrap_secret("") == ""
    assert unwrap_secret("") == ""


def test_tamper_raises():
    from cryptography.fernet import InvalidToken
    token = wrap_secret("sk-abcdef")
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        unwrap_secret(bad)


def test_different_inputs_different_tokens():
    assert wrap_secret("a") != wrap_secret("b")
    # But same input gives different token (Fernet adds a timestamp/nonce)
    assert wrap_secret("a") != wrap_secret("a")
