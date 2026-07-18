"""User-facing read endpoint for the new-account announcement popup. Admin CRUD lives in routers/admin.py."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import get_session
from models.user import User
from models.new_user_announcement import NewUserAnnouncement
from auth.dependencies import get_current_user
from schemas.auth import NewUserPopupResponse

router = APIRouter(tags=["new-user-popup"])


@router.get("/new-user-popup", response_model=Optional[NewUserPopupResponse])
def get_new_user_popup(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not user.show_new_user_popup:
        return None
    announcement = session.exec(select(NewUserAnnouncement)).first()
    if not announcement or not announcement.is_enabled:
        return None
    return NewUserPopupResponse(html_content=announcement.html_content)
