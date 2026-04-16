from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, h: str) -> bool:
    try:
        _ph.verify(h, pw)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False
