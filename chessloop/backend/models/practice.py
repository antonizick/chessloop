from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, UniqueConstraint


class PracticePosition(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "line_id", "move_index", name="uq_user_line_move"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    line_id: UUID = Field(foreign_key="line.id", index=True)
    move_index: int
    position_key: str = Field(index=True)
    ease_factor: float = 2.5
    interval_days: float = 0
    due_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    repetitions: int = 0
    leech_count: int = 0
    is_leech: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_reviewed: Optional[datetime] = None


class ReviewLog(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    practice_pos_id: UUID = Field(foreign_key="practiceposition.id", index=True)
    session_id: Optional[UUID] = Field(default=None, foreign_key="practicesession.id")
    was_correct: bool
    ease_chosen: Optional[str] = None  # 'easy' | 'hard'
    response_ms: Optional[int] = None
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)


class PracticeSession(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    mode: str  # 'weakest' | 'selected' | 'leech_drill'
    scope: str = "{}"  # JSON
    stats: str = "{}"  # JSON
