from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
import json


class LineCreate(BaseModel):
    name: Optional[str] = None
    starting_fen: Optional[str] = None


class LineUpdate(BaseModel):
    name: Optional[str] = None


class LineMoveAppend(BaseModel):
    san: str
    uci: str
    fen_after: str
    note: Optional[str] = None


class LineMoveNoteUpdate(BaseModel):
    text: str


class LineResponse(BaseModel):
    id: UUID
    library_id: UUID
    name: Optional[str]
    starting_fen: str
    moves: list[dict[str, Any]] = Field(default_factory=list)
    order_index: int
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
