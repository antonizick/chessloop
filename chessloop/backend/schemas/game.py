from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
import json


class GameCreate(BaseModel):
    name: str
    played_date: Optional[date] = None
    played_color: str = "white"  # 'white' | 'black'
    opponent_level: Optional[int] = None
    result: str = "win"  # 'win' | 'loss' | 'draw'
    what_happened: Optional[str] = None
    lesson_learned: Optional[str] = None
    repeat_offense: bool = False
    starting_fen: Optional[str] = None
    moves: list[str] = Field(default_factory=list)  # ordered SANs from the PGN


class GameUpdate(BaseModel):
    name: Optional[str] = None
    played_date: Optional[date] = None
    played_color: Optional[str] = None
    opponent_level: Optional[int] = None
    result: Optional[str] = None
    what_happened: Optional[str] = None
    lesson_learned: Optional[str] = None
    repeat_offense: Optional[bool] = None


class GameMovesImport(BaseModel):
    moves: list[str]
    starting_fen: Optional[str] = None


class GameMoveNoteUpdate(BaseModel):
    text: str


class GameMoveAppend(BaseModel):
    san: str
    uci: Optional[str] = None
    fen_after: Optional[str] = None
    note: Optional[str] = None


class GameResponse(BaseModel):
    id: UUID
    owner_user_id: UUID
    name: str
    played_date: Optional[date]
    played_color: str
    opponent_level: Optional[int]
    result: str
    what_happened: Optional[str]
    lesson_learned: Optional[str]
    repeat_offense: bool
    starting_fen: str
    moves: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("moves", mode="before")
    @classmethod
    def _parse_moves(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v or []
