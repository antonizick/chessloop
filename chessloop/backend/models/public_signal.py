from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class PublicSignal(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    target_type: str  # 'library'
    target_id: UUID = Field(index=True)
    kind: str  # 'star' | 'comment'
    content: Optional[str] = None  # for comments only
    created_at: datetime = Field(default_factory=datetime.utcnow)
