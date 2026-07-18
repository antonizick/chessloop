from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from jose import jwt, JWTError
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


def create_access_token(user_id: UUID) -> str:
    return _encode(str(user_id), timedelta(minutes=settings.access_ttl_min), "access")


def create_refresh_token(user_id: UUID) -> str:
    return _encode(str(user_id), timedelta(days=settings.refresh_ttl_days), "refresh")


def create_mfa_challenge_token(user_id: UUID) -> str:
    return _encode(str(user_id), timedelta(minutes=5), "mfa_challenge")


def create_email_verification_token(user_id: UUID) -> str:
    return _encode(str(user_id), timedelta(hours=24), "email_verify")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "create_mfa_challenge_token",
    "create_email_verification_token",
    "decode_token",
    "JWTError",
]
