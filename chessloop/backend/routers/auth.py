from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from database import get_session
from models import User
from auth.password import hash_password, verify_password
from services.activity_log import log_activity
from auth import jwt as jwt_utils
from auth import mfa
from auth.dependencies import get_current_user
from schemas.auth import (
    RegisterRequest,
    LoginRequest,
    MfaLoginRequest,
    RefreshRequest,
    TokenResponse,
    MfaChallengeResponse,
    MfaSetupResponse,
    MfaConfirmRequest,
    UserResponse,
    PreferencesRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)):
    existing = session.exec(
        select(User).where((User.email == body.email) | (User.username == body.username))
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already taken")
    user = User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    log_activity(session, user.id, user.username, "register")
    return user


@router.post("/login", response_model=TokenResponse | MfaChallengeResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.mfa_enabled:
        return MfaChallengeResponse(challenge_token=jwt_utils.create_mfa_challenge_token(user.id))

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    log_activity(session, user.id, user.username, "login")
    return TokenResponse(
        access_token=jwt_utils.create_access_token(user.id),
        refresh_token=jwt_utils.create_refresh_token(user.id),
    )


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
    if not mfa.verify(user.mfa_secret, body.totp_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid TOTP code")

    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    log_activity(session, user.id, user.username, "login", detail="via MFA")
    return TokenResponse(
        access_token=jwt_utils.create_access_token(user.id),
        refresh_token=jwt_utils.create_refresh_token(user.id),
    )


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
    return TokenResponse(
        access_token=jwt_utils.create_access_token(user.id),
        refresh_token=jwt_utils.create_refresh_token(user.id),
    )


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
    if not mfa.verify(user.mfa_secret, body.totp_code):
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
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
