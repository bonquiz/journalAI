from app.auth.password import hash_password, verify_password


def test_hash_verifies():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_hash_is_random():
    assert hash_password("x") != hash_password("x")


def test_verify_rejects_invalid_hash():
    # argon2 raises on malformed hash; our helper should return False.
    assert verify_password("anything", "not-a-real-hash") is False
