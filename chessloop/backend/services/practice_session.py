"""Practice session orchestration: position seeding + next-position selection.

Two responsibilities:

1. `ensure_positions_for_library`: idempotently create PracticePosition rows
   for every drillable move in a library's lines. A move is drillable for the
   user if it's their turn at that ply, per library color ("white", "black",
   or "both").

2. `select_next_position`: given a user, mode, and scope, return the next
   PracticePosition to drill. Implements the priority rules from the planning
   doc:
       - Overdue items sorted by most-overdue
       - Leeches always elevated
       - New items mixed in at 20% probability
       - Weakness bias (ease < 1.8) doubles selection weight
"""
from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Session, select

from models import Library, Line, PracticePosition
from services.position_key import canonical_position_key, active_color
from services.srs_engine import WEAKNESS_EASE_THRESHOLD

# Selection-weight constants. Tunable without touching algorithm logic.
LEECH_WEIGHT_BONUS = 3.0
WEAKNESS_WEIGHT_BONUS = 2.0
NEW_ITEM_PROBABILITY = 0.20
OVERDUE_HOURS_SCALE = 24.0  # 1 day overdue → 2x baseline
OVERDUE_HOURS_CAP = 120.0   # 5 days = max overdue boost


def ensure_positions_for_library(
    db: Session, user_id: UUID, library: Library
) -> int:
    """Create PracticePosition rows for every drillable move in this library.

    Idempotent — uses the (user_id, line_id, move_index) UNIQUE constraint
    implicitly by checking first. Returns the number of new rows created.
    """
    created = 0
    lines = db.exec(select(Line).where(Line.library_id == library.id)).all()

    for line in lines:
        moves = json.loads(line.moves or "[]")
        for i, _ in enumerate(moves):
            # Position BEFORE move i — what the user sees to find move i
            if i == 0:
                fen_before = line.starting_fen
            else:
                # Get fen_after from previous move
                prev_move = moves[i - 1]
                fen_before = prev_move.get("fen_after") if isinstance(prev_move, dict) else None

            # Skip if we can't get a valid FEN position
            if not fen_before:
                continue

            # Drillability: user only drills moves for their library's color
            turn = active_color(fen_before)
            if library.color != "both" and library.color != turn:
                continue

            existing = db.exec(
                select(PracticePosition).where(
                    PracticePosition.user_id == user_id,
                    PracticePosition.line_id == line.id,
                    PracticePosition.move_index == i,
                )
            ).first()
            if existing:
                continue

            db.add(
                PracticePosition(
                    user_id=user_id,
                    line_id=line.id,
                    move_index=i,
                    position_key=canonical_position_key(fen_before),
                )
            )
            created += 1

    if created:
        db.commit()
    return created


def _apply_learned_only(
    db: Session, line_ids: list[UUID], scope: dict
) -> list[UUID]:
    """Restrict a line-id list to learned lines when scope.learned_only is truthy."""
    if not scope.get("learned_only") or not line_ids:
        return line_ids
    return db.exec(
        select(Line.id).where(Line.id.in_(line_ids), Line.is_learned == True)  # noqa: E712
    ).all() or []


def _resolve_scope_line_ids(
    db: Session, user_id: UUID, mode: str, scope: dict
) -> Optional[list[UUID]]:
    """Return the line-id whitelist for this mode/scope, or None for 'all the user's lines'."""
    if mode == "selected":
        line_ids = [UUID(x) if isinstance(x, str) else x for x in scope.get("line_ids", [])]
        library_ids = [UUID(x) if isinstance(x, str) else x for x in scope.get("library_ids", [])]
        if library_ids:
            lib_lines = db.exec(
                select(Line.id).where(Line.library_id.in_(library_ids))
            ).all()
            line_ids = list({*line_ids, *lib_lines})
        return _apply_learned_only(db, line_ids or [], scope)

    if mode in ("weakest", "leech_drill"):
        # Restrict to the picked libraries if the key is present (even an
        # empty pick means "none"), else ACTIVE libraries owned by this user —
        # preserves default behavior for callers that omit library_ids
        # entirely (e.g. the dashboard's "practice weakest now" shortcut).
        if "library_ids" in scope:
            picked = [UUID(x) if isinstance(x, str) else x for x in scope["library_ids"]]
            if not picked:
                return []
            lib_ids = db.exec(
                select(Library.id).where(
                    Library.id.in_(picked),
                    Library.owner_user_id == user_id,
                )
            ).all()
        else:
            lib_ids = db.exec(
                select(Library.id).where(
                    Library.owner_user_id == user_id,
                    Library.is_active == True,  # noqa: E712
                )
            ).all()
        if not lib_ids:
            return []
        line_ids = db.exec(
            select(Line.id).where(Line.library_id.in_(lib_ids))
        ).all() or []
        return _apply_learned_only(db, line_ids, scope)

    return None


def select_next_position(
    db: Session,
    user_id: UUID,
    mode: str,
    scope: dict,
    now: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> Optional[PracticePosition]:
    """Pick the next position to drill, or None if nothing is due/available.

    `rng` lets tests pass in a seeded Random for determinism.

    scope.start_position controls which positions are eligible:
      "first"  — only the earliest move_index in the candidate set (start
                 every line from the beginning).
      "random" — uniform random pick; ignores SRS weights.
      "mixed"  — 50/50 per round: either "first" or the normal SRS selection.
      absent / anything else — normal SRS-weighted selection (default).
    """
    now = now or datetime.utcnow()
    rng = rng or random

    line_ids = _resolve_scope_line_ids(db, user_id, mode, scope)
    if line_ids is not None and not line_ids:
        return None

    q = select(PracticePosition).where(PracticePosition.user_id == user_id)
    if line_ids is not None:
        q = q.where(PracticePosition.line_id.in_(line_ids))

    if mode == "leech_drill":
        leeches = db.exec(q.where(PracticePosition.is_leech == True)).all()  # noqa: E712
        if not leeches:
            return None
        leeches.sort(key=lambda p: p.due_at)
        return leeches[0]

    start_pos = scope.get("start_position", "auto")

    # "mixed" flips a coin each round
    if start_pos == "mixed":
        start_pos = rng.choice(["first", "auto"])

    all_positions = db.exec(q).all()
    if not all_positions:
        return None

    # "first" — filter to the earliest move_index in the candidate set, then
    # pick uniformly so every line's opening position gets equal exposure.
    if start_pos == "first":
        min_idx = min(p.move_index for p in all_positions)
        first_positions = [p for p in all_positions if p.move_index == min_idx]
        return rng.choice(first_positions)

    # "random" — uniform pick regardless of SRS state
    if start_pos == "random":
        return rng.choice(all_positions)

    # Default: weighted SRS selection
    due = [p for p in all_positions if p.due_at <= now and p.repetitions > 0]
    new_items = [p for p in all_positions if p.repetitions == 0]

    # 20% chance of preferring a new item, provided some exist.
    # Also: if nothing is due, always serve new (no point waiting).
    prefer_new = bool(new_items) and (not due or rng.random() < NEW_ITEM_PROBABILITY)
    if prefer_new:
        return rng.choice(new_items)

    if not due:
        return rng.choice(new_items) if new_items else None

    return _weighted_pick_from_due(due, now, rng)


def _weighted_pick_from_due(
    due: list[PracticePosition],
    now: datetime,
    rng: random.Random,
) -> PracticePosition:
    """Weighted random pick from due positions. Heavier weight = more likely."""
    weighted: list[tuple[float, PracticePosition]] = []
    for p in due:
        w = 1.0
        if p.is_leech:
            w *= LEECH_WEIGHT_BONUS
        if p.ease_factor < WEAKNESS_EASE_THRESHOLD:
            w *= WEAKNESS_WEIGHT_BONUS
        overdue_hours = max(0.0, (now - p.due_at).total_seconds() / 3600.0)
        # Linear boost up to a cap so a 30-day-overdue card doesn't crowd out everything
        boost = 1.0 + min(overdue_hours / OVERDUE_HOURS_SCALE, OVERDUE_HOURS_CAP / OVERDUE_HOURS_SCALE)
        w *= boost
        weighted.append((w, p))

    total = sum(w for w, _ in weighted)
    r = rng.uniform(0, total)
    cumulative = 0.0
    for w, p in weighted:
        cumulative += w
        if r <= cumulative:
            return p
    return weighted[-1][1]
