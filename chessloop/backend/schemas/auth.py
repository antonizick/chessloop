from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator
from email_validator import validate_email, EmailNotValidError

from config import settings


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_deliverable(cls, v: str) -> str:
        # EmailStr only checks syntax — this adds an MX lookup so registration
        # rejects addresses at domains that can't receive mail at all.
        # Gated by settings so tests/offline self-hosts aren't network-dependent.
        if not settings.email_mx_check:
            return v
        try:
            validate_email(v, check_deliverability=True)
        except EmailNotValidError as e:
            raise ValueError(str(e))
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MfaLoginRequest(BaseModel):
    challenge_token: str
    totp_code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MfaChallengeResponse(BaseModel):
    mfa_required: bool = True
    challenge_token: str


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_code_b64: str


class MfaConfirmRequest(BaseModel):
    totp_code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterResponse(BaseModel):
    email: EmailStr
    message: str = "Check your email to verify your account."


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class PreferencesRequest(BaseModel):
    theme: Optional[str] = None
    piece_set: Optional[str] = None
    board_theme: Optional[str] = None
    sounds_on: Optional[bool] = None
    tts_enabled: Optional[bool] = None
    tts_voice: Optional[str] = None
    boost_visibility: Optional[bool] = None


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    role: str
    mfa_enabled: bool
    theme: str
    piece_set: str
    board_theme: str
    sounds_on: bool
    tts_enabled: bool
    tts_voice: str
    boost_visibility: bool
    created_at: datetime
    last_login: Optional[datetime] = None
