from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class PublicLibraryEntry(BaseModel):
    id: UUID
    name: str
    color: str
    description: Optional[str] = None
    eco_code: Optional[str] = None
    difficulty: Optional[str] = None
    owner_username: str
    published_at: datetime
    star_count: int
    line_count: int
    forked_from_id: Optional[UUID] = None


class CommentEntry(BaseModel):
    id: UUID
    username: str
    content: str
    created_at: datetime


class PublicLibraryDetail(BaseModel):
    id: UUID
    name: str
    color: str
    description: Optional[str] = None
    eco_code: Optional[str] = None
    difficulty: Optional[str] = None
    owner_username: str
    published_at: datetime
    star_count: int
    line_count: int
    forked_from_id: Optional[UUID] = None
    user_has_starred: bool
    comments: list[CommentEntry]


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
