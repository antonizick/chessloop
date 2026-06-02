from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class PublishedLibrary(SQLModel, table=True):
    """Immutable snapshot of a library at time of publication."""
    __tablename__ = "published_library"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    original_library_id: Optional[UUID] = Field(default=None, index=True)  # Reference only, no FK cascade
    name: str
    color: str  # 'white' | 'black' | 'both'
    description: Optional[str] = None
    eco_code: Optional[str] = Field(default=None, index=True)
    difficulty: Optional[str] = None  # 'beginner'|'intermediate'|'advanced'
    published_by_user_id: UUID = Field(foreign_key="user.id", index=True)
    published_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PublishedLine(SQLModel, table=True):
    """A line within a published library."""
    __tablename__ = "published_line"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    published_library_id: UUID = Field(foreign_key="published_library.id", index=True)
    original_line_id: Optional[UUID] = Field(default=None, index=True)  # Reference only, no FK cascade
    name: Optional[str] = None
    starting_fen: str = Field(default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    moves: str  # JSON array: [{san, uci, fen_after, note}]
    order_index: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
