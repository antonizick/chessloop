from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class Line(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    library_id: UUID = Field(foreign_key="library.id", index=True)
    name: Optional[str] = None
    starting_fen: str = Field(default=STARTING_FEN)
    moves: str = Field(default="[]")  # JSON array of {san, uci, fen_after, note?}
    order_index: int = 0
    is_learned: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MoveNote(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    line_id: UUID = Field(foreign_key="line.id", index=True)
    move_num: int
    text: str
    is_public: bool = False
    author_id: UUID = Field(foreign_key="user.id")
