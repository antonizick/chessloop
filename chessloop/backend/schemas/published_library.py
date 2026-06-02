from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, HttpUrl


class PublishedLineResponse(BaseModel):
    id: UUID
    name: Optional[str]
    starting_fen: str
    moves: str
    order_index: int
    created_at: datetime


class PublishedLibraryResponse(BaseModel):
    id: UUID
    original_library_id: Optional[UUID]
    name: str
    color: str
    description: Optional[str]
    eco_code: Optional[str]
    difficulty: Optional[str]
    published_by_user_id: UUID
    published_at: datetime
    created_at: datetime


class PublishedLibraryDetail(BaseModel):
    id: UUID
    original_library_id: Optional[UUID]
    name: str
    color: str
    description: Optional[str]
    eco_code: Optional[str]
    difficulty: Optional[str]
    published_by_user_id: UUID
    published_at: datetime
    created_at: datetime
    lines: list[PublishedLineResponse] = []
    video_links: list = []  # Will be populated from PublishedLibraryVideoLink
