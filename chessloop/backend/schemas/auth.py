from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


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


class MfaConfirmRequest(BaseModel):
    totp_code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class PreferencesRequest(BaseModel):
    theme: Optional[str] = None
    piece_set: Optional[str] = None
    board_theme: Optional[str] = None
    sounds_on: Optional[bool] = None


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
    created_at: datetime
    last_login: Optional[datetime] = None
