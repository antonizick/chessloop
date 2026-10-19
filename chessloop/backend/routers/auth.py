import logging
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from database import get_session
from models import User
from models.published_library import PublishedLibrary
from auth.password import hash_password, verify_password
from auth.policy import RateLimiter, client_ip, password_problem, verification_required, PASSWORD_MIN_LENGTH
from config import settings
from services.activity_log import log_activity
from services.library_service import clone_library_for_user
from services.email_service import send_verification_email, send_password_reset_email
from auth import jwt as jwt_utils
from auth import mfa
from auth.dependencies import get_current_user
from schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    MfaLoginRequest,
    RefreshRequest,
    TokenResponse,
    MfaChallengeResponse,
    MfaSetupResponse,
    MfaConfirmRequest,
    UserResponse,
    PreferencesRequest,
    VerifyEmailRequest,
    ResendVerificationRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    AuthConfigResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Failed current-password attempts on /change-password, per user and per client IP.
# lucent: ceiling is 5 failures per 15 minutes; a correct attempt does not count.
CHANGE_PASSWORD_LIMIT = RateLimiter(max_events=5, window_seconds=15 * 60)
# Wrong authenticator codes per account (sign-in and turning MFA off). Without a
# limit, someone who knows the password could try all million codes.
MFA_CODE_LIMIT = RateLimiter(max_events=5, window_seconds=15 * 60)
MFA_LOCKED = "Too many wrong codes. Wait 15 minutes and try again."


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=jwt_utils.create_access_token(user.id, user.token_version),
        refresh_token=jwt_utils.create_refresh_token(user.id, user.token_version),
    )


def _require_strong(password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)


@router.get("/config", response_model=AuthConfigResponse)
def auth_config(session: Session = Depends(get_session)):
    return AuthConfigResponse(
        registration_open=True,
        email_verification=verification_required(session),
        smtp_configured=settings.smtp_configured,
        password_min_length=PASSWORD_MIN_LENGTH,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(
        select(User).where((User.email == body.email) | (User.username == body.username))
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already taken")
    _require_strong(body.password)
    enforce_verification = verification_required(session)
    user = User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
        show_new_user_popup=True,
        is_verified=not enforce_verification,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Clone 'Ruy López — Closed' to the new user's library
    try:
        published_lib = session.exec(
            select(PublishedLibrary).where(PublishedLibrary.name == "Ruy López — Closed")
        ).first()
        if published_lib and published_lib.original_library_id:
            clone_library_for_user(published_lib.original_library_id, user.id, session)
            session.commit()
    except Exception as e:
        # Log but don't fail registration if cloning fails
        logger.warning(f"Failed to clone default opening for user {user.id}: {e}")

    log_activity(session, user.id, user.username, "register")
    if enforce_verification:
        if not settings.smtp_configured:
            logger.warning(
                "Email verification is required but SMTP is not configured: %s must be "
                "verified by an admin (Admin → Users) before they can log in", user.email,
            )
            return RegisterResponse(
                email=user.email,
                message="Account created. This server can't send email, so ask your ChessLoop "
                        "admin to verify your account before you log in.",
                next_step="ask_admin",
            )
        send_verification_email(user.email, jwt_utils.create_email_verification_token(user.id))
        return RegisterResponse(email=user.email)
    return RegisterResponse(email=user.email, message="Account created. You can log in now.", next_step="login")


@router.post("/login", response_model=TokenResponse | MfaChallengeResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")

    if user.mfa_enabled:
        return MfaChallengeResponse(challenge_token=jwt_utils.create_mfa_challenge_token(user.id))

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    log_activity(session, user.id, user.username, "login")
    return _issue_tokens(user)


@router.post("/login/mfa", response_model=TokenResponse)
def login_mfa(body: MfaLoginRequest, session: Session = Depends(get_session)):
    try:
        payload = jwt_utils.decode_token(body.challenge_token)
    except jwt_utils.JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid challenge")
    if payload.get("type") != "mfa_challenge":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    user = session.get(User, UUID(payload["sub"]))
    if not user or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA not configured")
    key = f"mfa:{user.id}"
    if MFA_CODE_LIMIT.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MFA_LOCKED)
    if not mfa.verify(user.mfa_secret, body.totp_code):
        MFA_CODE_LIMIT.hit(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid TOTP code")

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    log_activity(session, user.id, user.username, "login", detail="via MFA")
    return _issue_tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(_: User = Depends(get_current_user)):
    return None


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, session: Session = Depends(get_session)):
    try:
        payload = jwt_utils.decode_token(body.refresh_token)
    except jwt_utils.JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    user = session.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if not jwt_utils.token_version_matches(payload, user.token_version):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again")
    return _issue_tokens(user)


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(body: VerifyEmailRequest, session: Session = Depends(get_session)):
    try:
        payload = jwt_utils.decode_token(body.token)
    except jwt_utils.JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired verification link")
    if payload.get("type") != "email_verify":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    user = session.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    if user.is_verified:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This verification link has already been used")

    user.is_verified = True
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    log_activity(session, user.id, user.username, "verify_email")

    return _issue_tokens(user)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification(body: ResendVerificationRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if user and not user.is_verified:
        send_verification_email(user.email, jwt_utils.create_email_verification_token(user.id))
    # Always 204 regardless of whether the account exists/is already verified —
    # lucent: avoid leaking account existence via response differences


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(body: ForgotPasswordRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if user:
        send_password_reset_email(
            user.email, jwt_utils.create_password_reset_token(user.id, user.password_hash)
        )
    # Always 204 regardless of whether the account exists —
    # lucent: avoid leaking account existence via response differences


def _resolve_reset_token(token: str, session: Session) -> User:
    try:
        payload = jwt_utils.decode_token(token)
    except jwt_utils.JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired reset link")
    if payload.get("type") != "pwd_reset":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    user = session.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    if payload.get("pwh") != jwt_utils.password_hash_fingerprint(user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This reset link has already been used")

    return user


@router.get("/reset-password/validate", status_code=status.HTTP_204_NO_CONTENT)
def validate_reset_token(token: str, session: Session = Depends(get_session)):
    # Read-only check so the frontend can tell a dead link from a live one
    # before showing the "choose a new password" form — no state is touched.
    _resolve_reset_token(token, session)


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(body: ResetPasswordRequest, session: Session = Depends(get_session)):
    user = _resolve_reset_token(body.token, session)
    _require_strong(body.new_password)

    mfa_disabled = body.disable_mfa and user.mfa_enabled
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    user.last_login = datetime.utcnow()
    if mfa_disabled:
        user.mfa_enabled = False
        user.mfa_secret = None
    session.add(user)
    session.commit()
    log_activity(
        session, user.id, user.username, "password_reset",
        detail="mfa_disabled" if mfa_disabled else None,
    )

    return _issue_tokens(user)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    keys = [f"user:{user.id}", f"ip:{client_ip(request)}"]
    if any(CHANGE_PASSWORD_LIMIT.blocked(k) for k in keys):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait 15 minutes and try again."
        )
    if not verify_password(body.current_password, user.password_hash):
        for k in keys:
            CHANGE_PASSWORD_LIMIT.hit(k)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "The new password must be different from the current one."
        )
    _require_strong(body.new_password)

    user.password_hash = hash_password(body.new_password)
    # Invalidates every access and refresh token issued before this moment,
    # including other devices' sessions; the caller gets fresh ones below.
    user.token_version += 1
    session.add(user)
    session.commit()
    session.refresh(user)
    log_activity(session, user.id, user.username, "password_change")
    return _issue_tokens(user)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA already enabled")
    secret = mfa.new_secret()
    user.mfa_secret = secret
    session.add(user)
    session.commit()
    otpauth_url = mfa.provisioning_uri(secret, user.email)
    return MfaSetupResponse(
        secret=secret,
        otpauth_url=otpauth_url,
        qr_code_b64=mfa.qr_code_b64(otpauth_url),
    )


@router.post("/mfa/confirm", status_code=status.HTTP_204_NO_CONTENT)
def mfa_confirm(
    body: MfaConfirmRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA not set up")
    if not mfa.verify(user.mfa_secret, body.totp_code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid TOTP code")
    user.mfa_enabled = True
    session.add(user)
    session.commit()


@router.delete("/mfa", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(
    body: MfaConfirmRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA not enabled")
    key = f"mfa:{user.id}"
    if MFA_CODE_LIMIT.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MFA_LOCKED)
    if not mfa.verify(user.mfa_secret, body.totp_code):
        MFA_CODE_LIMIT.hit(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid TOTP code")
    user.mfa_enabled = False
    user.mfa_secret = None
    session.add(user)
    session.commit()


_VALID_THEMES = {"dark", "light"}
_VALID_PIECE_SETS = {"cburnett", "alpha", "mono", "shadow"}
_VALID_BOARD_THEMES = {"brown", "blue", "green", "ice", "purple"}


@router.patch("/preferences", response_model=UserResponse)
def update_preferences(
    body: PreferencesRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if body.theme is not None:
        if body.theme not in _VALID_THEMES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid theme. Choose from: {', '.join(_VALID_THEMES)}")
        user.theme = body.theme
    if body.piece_set is not None:
        if body.piece_set not in _VALID_PIECE_SETS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid piece_set. Choose from: {', '.join(_VALID_PIECE_SETS)}")
        user.piece_set = body.piece_set
    if body.board_theme is not None:
        if body.board_theme not in _VALID_BOARD_THEMES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid board_theme. Choose from: {', '.join(_VALID_BOARD_THEMES)}")
        user.board_theme = body.board_theme
    if body.sounds_on is not None:
        user.sounds_on = body.sounds_on
    if body.tts_enabled is not None:
        user.tts_enabled = body.tts_enabled
    if body.tts_voice is not None:
        user.tts_voice = body.tts_voice
    if body.boost_visibility is not None:
        user.boost_visibility = body.boost_visibility
    if body.show_new_user_popup is not None:
        user.show_new_user_popup = body.show_new_user_popup
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
