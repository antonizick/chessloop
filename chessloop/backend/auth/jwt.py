import hashlib
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import jwt
from jwt import PyJWTError as JWTError
from config import settings


def _encode(sub: str, ttl: timedelta, token_type: str, extra: Optional[dict] = None) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# Access and refresh tokens carry the user's token_version ("tv"). Bumping
# User.token_version (password change or reset) makes every token issued before
# it fail, so a stolen session dies with the old password. Tokens from before
# this claim existed have no "tv" and count as version 0.
def create_access_token(user_id: UUID, token_version: int = 0) -> str:
    return _encode(
        str(user_id), timedelta(minutes=settings.access_ttl_min), "access", extra={"tv": token_version}
    )


def create_refresh_token(user_id: UUID, token_version: int = 0) -> str:
    return _encode(
        str(user_id), timedelta(days=settings.refresh_ttl_days), "refresh", extra={"tv": token_version}
    )


def token_version_matches(payload: dict, current_version: int) -> bool:
    return payload.get("tv", 0) == current_version


def create_mfa_challenge_token(user_id: UUID) -> str:
    return _encode(str(user_id), timedelta(minutes=5), "mfa_challenge")


def create_email_verification_token(user_id: UUID) -> str:
    return _encode(str(user_id), timedelta(hours=24), "email_verify")


def password_hash_fingerprint(password_hash: str) -> str:
    # Binds a reset token to the password hash at issue time, so the token
    # stops matching (and is rejected) the instant the password is changed —
    # single-use without needing a persisted token/used-flag column.
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_password_reset_token(user_id: UUID, password_hash: str) -> str:
    return _encode(
        str(user_id),
        timedelta(hours=1),
        "pwd_reset",
        extra={"pwh": password_hash_fingerprint(password_hash)},
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "create_mfa_challenge_token",
    "create_email_verification_token",
    "create_password_reset_token",
    "password_hash_fingerprint",
    "token_version_matches",
    "decode_token",
    "JWTError",
]
