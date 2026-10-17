from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator
from email_validator import validate_email, EmailNotValidError

from config import settings


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(max_length=128)  # strength rule: auth.policy.password_problem

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
    # What the UI should tell the person to do: check_email | ask_admin | login
    next_step: str = "check_email"


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(max_length=128)
    disable_mfa: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class AuthConfigResponse(BaseModel):
    """Public, secret-free facts the login/register pages need."""
    registration_open: bool
    email_verification: bool
    smtp_configured: bool
    password_min_length: int


class PreferencesRequest(BaseModel):
    theme: Optional[str] = None
    piece_set: Optional[str] = None
    board_theme: Optional[str] = None
    sounds_on: Optional[bool] = None
    tts_enabled: Optional[bool] = None
    tts_voice: Optional[str] = None
    boost_visibility: Optional[bool] = None
    show_new_user_popup: Optional[bool] = None


class NewUserPopupContent(BaseModel):
    html_content: str
    is_enabled: bool


class NewUserPopupResponse(BaseModel):
    html_content: str


class BannerContent(BaseModel):
    html_content: str
    is_enabled: bool


class BannerResponse(BaseModel):
    html_content: str
    version: int


class SystemSettingsContent(BaseModel):
    enforce_email_verification: bool


class SystemSettingsUpdate(BaseModel):
    # null clears the admin's choice so CHESSLOOP_EMAIL_VERIFICATION decides again
    enforce_email_verification: Optional[bool]


class SystemSettingsResponse(BaseModel):
    enforce_email_verification: bool  # the effective value
    source: str                       # 'admin' (set here) or 'config' (.env)
    config_mode: str                  # CHESSLOOP_EMAIL_VERIFICATION: auto | on | off
    smtp_configured: bool             # never the SMTP host or credentials


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
