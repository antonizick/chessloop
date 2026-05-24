from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = Field(pattern="^(white|black|both)$")
    description: Optional[str] = None
    eco_code: Optional[str] = None
    difficulty: Optional[str] = Field(default=None, pattern="^(beginner|intermediate|advanced)$")


class LibraryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern="^(white|black|both)$")
    description: Optional[str] = None
    eco_code: Optional[str] = None
    difficulty: Optional[str] = Field(default=None, pattern="^(beginner|intermediate|advanced)$")


class LibraryActiveToggle(BaseModel):
    is_active: bool


class LibraryResponse(BaseModel):
    id: UUID
    name: str
    color: str
    owner_user_id: UUID
    is_active: bool
    is_public: bool
    forked_from_id: Optional[UUID] = None
    published_at: Optional[datetime] = None
    description: Optional[str] = None
    eco_code: Optional[str] = None
    difficulty: Optional[str] = None
    created_at: datetime
    updated_at: datetime
