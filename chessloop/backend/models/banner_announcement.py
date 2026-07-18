from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class BannerAnnouncement(SQLModel, table=True):
    """Site-wide banner shown on every page. `version` bumps on content change so
    every user's per-account dismissal (User.banner_dismissed_version) goes stale
    and the banner reappears — no need to reset every user row."""

    __tablename__ = "banner_announcement"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    html_content: str = Field(default="")
    is_enabled: bool = False
    version: int = Field(default=1)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
