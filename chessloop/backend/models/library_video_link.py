from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class LibraryVideoLink(SQLModel, table=True):
    __tablename__ = "library_video_link"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    library_id: UUID = Field(foreign_key="library.id", index=True)
    title: str
    url: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
