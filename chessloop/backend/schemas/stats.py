from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class HeatmapBucket(BaseModel):
    move_number: int   # 1-indexed
    total: int
    correct: int
    accuracy: float    # 0.0 – 1.0


class HeatmapResponse(BaseModel):
    by_move_number: list[HeatmapBucket]


class MasteryEntry(BaseModel):
    library_id: UUID
    library_name: str
    color: str
    total_positions: int
    mastered_positions: int
    mastery_pct: float   # 0.0 – 100.0
    badge: str           # 'not_started' | 'learning' | 'developing' | 'advanced' | 'mastered'


class MasteryResponse(BaseModel):
    libraries: list[MasteryEntry]


class LeechEntry(BaseModel):
    practice_position_id: UUID
    line_id: UUID
    line_name: Optional[str]
    library_id: UUID
    library_name: str
    move_index: int
    leech_count: int
    ease_factor: float


class RecentSession(BaseModel):
    id: UUID
    mode: str
    started_at: str
    ended_at: Optional[str] = None
    correct: int
    wrong: int
    positions_seen: int
