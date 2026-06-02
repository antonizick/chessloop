from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlmodel import Session
from models.activity_log import ActivityLog


def log_activity(
    session: Session,
    user_id: Optional[UUID],
    username: str,
    action: str,
    target: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    try:
        entry = ActivityLog(
            user_id=user_id,
            username=username,
            action=action,
            target=target,
            detail=detail,
            timestamp=datetime.utcnow(),
        )
        session.add(entry)
        session.commit()
    except Exception:
        session.rollback()
