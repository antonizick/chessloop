from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class NewUserAnnouncement(SQLModel, table=True):
    __tablename__ = "new_user_announcement"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    html_content: str = Field(default="")
    is_enabled: bool = False
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[UUID] = Field(default=None, foreign_key="user.id")
