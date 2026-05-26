from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ── Session start ────────────────────────────────────────────────────────────

class SessionStartRequest(BaseModel):
    mode: Literal["weakest", "selected", "leech_drill"] = "weakest"
    scope: dict[str, Any] = Field(default_factory=dict)
    is_rated: bool = True


class SessionStartResponse(BaseModel):
    id: UUID
    mode: str
    scope: dict[str, Any]
    started_at: datetime
    seeded_positions: int  # how many new PracticePositions were materialized


# ── Next position ────────────────────────────────────────────────────────────

class PrecedingMove(BaseModel):
    san: str
    uci: str
    fen_after: str
    note: Optional[str] = None


class NextPositionResponse(BaseModel):
    done: Literal[False] = False
    practice_position_id: UUID
    line_id: UUID
    line_name: Optional[str]
    library_id: UUID
    library_name: str
    library_color: str  # "white" | "black" | "both"
    move_index: int
    starting_fen: str
    fen_before: str
    turn_color: Literal["white", "black"]
    preceding_moves: list[PrecedingMove]
    # Full mainline from move_index to the end of the line.
    # remaining_moves[0] is the user's challenge move (at move_index).
    # Odd-indexed entries are the computer's auto-replies; even-indexed
    # entries are the user's subsequent moves.
    remaining_moves: list[PrecedingMove]
    is_new: bool
    is_leech: bool
    repetitions: int
    ease_factor: float


class SessionDoneResponse(BaseModel):
    done: Literal[True] = True
    stats: dict[str, Any]


# ── Answer ───────────────────────────────────────────────────────────────────

class AnswerRequest(BaseModel):
    practice_position_id: UUID
    move_uci: str
    ease: Optional[Literal["easy", "hard"]] = None
    response_ms: Optional[int] = None
    # Full-line practice override: when set, skip the UCI comparison and use
    # this value directly to update SRS.  The move_uci is still recorded in
    # the ReviewLog for auditing.
    line_correct: Optional[bool] = None


class SrsState(BaseModel):
    ease_factor: float
    interval_days: float
    due_at: datetime
    repetitions: int
    leech_count: int
    is_leech: bool


class AnswerResponse(BaseModel):
    correct: bool
    expected_san: str
    expected_uci: str
    fen_after: str
    note: Optional[str] = None
    srs: SrsState


# ── Session end + dashboard ──────────────────────────────────────────────────

class SessionEndResponse(BaseModel):
    id: UUID
    ended_at: datetime
    stats: dict[str, Any]


class DueCountResponse(BaseModel):
    count: int
    new: int
    leeches: int
