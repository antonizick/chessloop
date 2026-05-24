from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class Library(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    color: str  # 'white' | 'black' | 'both'
    owner_user_id: UUID = Field(foreign_key="user.id", index=True)
    is_active: bool = True
    is_public: bool = Field(default=False, index=True)
    forked_from_id: Optional[UUID] = Field(default=None, foreign_key="library.id")
    published_at: Optional[datetime] = None
    description: Optional[str] = None
    eco_code: Optional[str] = Field(default=None, index=True)
    difficulty: Optional[str] = None  # 'beginner'|'intermediate'|'advanced'
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
