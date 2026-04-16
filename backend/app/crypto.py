"""API-key wrap/unwrap using Fernet + PBKDF2-derived key.

SECRET_KEY_WRAP is the operator-provided ENV (enforced to 64 hex chars).
We derive a 32-byte Fernet key via PBKDF2-HMAC-SHA256 (600k iterations),
which is resilient even if SECRET_KEY_WRAP has lower entropy than expected.
"""
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings


def _fernet() -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"journalai-wrap-v1",  # static salt is acceptable: one key per instance
        iterations=600_000,
    )
    raw = kdf.derive(settings.secret_key_wrap.encode())
    return Fernet(base64.urlsafe_b64encode(raw))


def wrap_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def unwrap_secret(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()
