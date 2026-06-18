from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class Game(SQLModel, table=True):
    """A user-uploaded played game with metadata + an annotated move list.

    Moves are stored exactly like Line.moves — a JSON array of
    {san, uci, fen_after, note?} — so the same board/navigation/notes engine
    used by the teaching boards works unchanged.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID = Field(foreign_key="user.id", index=True)
    name: str
    played_date: Optional[date] = None
    played_color: str = "white"  # 'white' | 'black'
    opponent_level: Optional[int] = None  # numeric rating, e.g. 1100
    result: str = "win"  # 'win' | 'loss' | 'draw'
    what_happened: Optional[str] = None
    lesson_learned: Optional[str] = None
    repeat_offense: bool = False
    starting_fen: str = Field(default=STARTING_FEN)
    moves: str = Field(default="[]")  # JSON array of {san, uci, fen_after, note?}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
