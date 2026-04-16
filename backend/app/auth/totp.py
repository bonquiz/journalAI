import pyotp

ISSUER = "journalAI"


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account: str = "journal") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=ISSUER)


def verify_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
