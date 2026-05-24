from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class Backup(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    type: str  # 'full' | 'content' | 'progress'
    file_path: str
    size_bytes: int = 0
    created_by: UUID = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
