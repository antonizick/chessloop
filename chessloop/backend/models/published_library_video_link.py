from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class PublishedLibraryVideoLink(SQLModel, table=True):
    """Video link attached to a published library (immutable copy at time of publication)."""
    __tablename__ = "published_library_video_link"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    published_library_id: UUID = Field(foreign_key="published_library.id", index=True)
    original_video_link_id: Optional[UUID] = Field(default=None, index=True)  # Reference only, no FK
    title: str
    url: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
