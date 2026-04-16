import pyotp

from app.auth.totp import generate_secret, provisioning_uri, verify_code


def test_verify_valid_code():
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code) is True


def test_verify_invalid_code():
    secret = generate_secret()
    assert verify_code(secret, "000000") is False


def test_provisioning_uri_contains_issuer():
    uri = provisioning_uri("JBSWY3DPEHPK3PXP")
    assert "journalAI" in uri
    assert "JBSWY3DPEHPK3PXP" in uri


def test_generate_secret_valid_base32():
    secret = generate_secret()
    assert len(secret) >= 16
    # pyotp secrets are base32-safe
    assert set(secret).issubset(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"))
