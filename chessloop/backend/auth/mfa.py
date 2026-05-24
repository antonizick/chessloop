import pyotp


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str, issuer: str = "ChessLoop") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def verify(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
