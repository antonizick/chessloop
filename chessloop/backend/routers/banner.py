"""User-facing read + dismiss for the site-wide banner. Admin CRUD lives in routers/admin.py."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_session
from models.user import User
from models.banner_announcement import BannerAnnouncement
from auth.dependencies import get_current_user
from schemas.auth import BannerResponse

router = APIRouter(tags=["banner"])


@router.get("/banner", response_model=Optional[BannerResponse])
def get_banner(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    announcement = session.exec(select(BannerAnnouncement)).first()
    if not announcement or not announcement.is_enabled:
        return None
    if user.banner_dismissed_version >= announcement.version:
        return None
    return BannerResponse(html_content=announcement.html_content, version=announcement.version)


@router.post("/banner/dismiss", status_code=204)
def dismiss_banner(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Permanent 'don't show again' — pins the user to the current banner version."""
    announcement = session.exec(select(BannerAnnouncement)).first()
    user.banner_dismissed_version = announcement.version if announcement else 0
    session.add(user)
    session.commit()
