from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class ActivityLog(SQLModel, table=True):
    __tablename__ = "activitylog"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(default=None, index=True)
    username: str = Field(default="unknown")
    action: str  # login, register, create_library, delete_library, fork_library, publish_library, create_line, delete_line
    target: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
