import json
from datetime import datetime
from typing import Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from database import get_session
from models import User, Library, Line, PracticePosition, ReviewLog, PracticeSession
from auth.dependencies import get_current_user
from services import srs_engine
from services.position_key import active_color
from services.practice_session import (
    ensure_positions_for_library,
    select_next_position,
)
from schemas.practice import (
    SessionStartRequest,
    SessionStartResponse,
    NextPositionResponse,
    SessionDoneResponse,
    PrecedingMove,
    AnswerRequest,
    AnswerResponse,
    SrsState,
    SessionEndResponse,
    DueCountResponse,
)

router = APIRouter(prefix="/practice", tags=["practice"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_active_session(db: Session, sid: UUID, user: User) -> PracticeSession:
    ps = db.get(PracticeSession, sid)
    if not ps:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if ps.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your session")
    if ps.ended_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Session already ended")
    return ps


def _libraries_to_seed(
    db: Session, user: User, mode: str, scope: dict
) -> list[Library]:
    """Find libraries whose PracticePositions must be materialized for this session."""
    if mode == "selected":
        lib_ids = [UUID(x) if isinstance(x, str) else x for x in scope.get("library_ids", [])]
        line_ids = [UUID(x) if isinstance(x, str) else x for x in scope.get("line_ids", [])]
        libs: dict[UUID, Library] = {}
        if lib_ids:
            for lib in db.exec(
                select(Library).where(
                    Library.id.in_(lib_ids),
                    Library.owner_user_id == user.id,
                )
            ).all():
                libs[lib.id] = lib
        if line_ids:
            line_rows = db.exec(select(Line).where(Line.id.in_(line_ids))).all()
            lib_ids_from_lines = {l.library_id for l in line_rows}
            for lib in db.exec(
                select(Library).where(
                    Library.id.in_(lib_ids_from_lines),
                    Library.owner_user_id == user.id,
                )
            ).all():
                libs[lib.id] = lib
        return list(libs.values())

    # weakest / leech_drill: all active libraries owned by user
    return db.exec(
        select(Library).where(
            Library.owner_user_id == user.id,
            Library.is_active == True,  # noqa: E712
        )
    ).all()


def _build_next_response(db: Session, pos: PracticePosition) -> NextPositionResponse:
    line = db.get(Line, pos.line_id)
    if not line:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Line vanished")
    lib = db.get(Library, line.library_id)
    if not lib:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Library vanished")

    moves = json.loads(line.moves or "[]")

    # Validate move structure and get fen_before
    if pos.move_index == 0:
        fen_before = line.starting_fen
    else:
        if pos.move_index > len(moves):
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Move index out of range")
        prev_move = moves[pos.move_index - 1]
        fen_before = prev_move.get("fen_after")
        if not fen_before:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Move missing fen_after field")

    return NextPositionResponse(
        practice_position_id=pos.id,
        line_id=line.id,
        line_name=line.name,
        library_id=lib.id,
        library_name=lib.name,
        library_color=lib.color,
        move_index=pos.move_index,
        starting_fen=line.starting_fen,
        fen_before=fen_before,
        turn_color=active_color(fen_before),
        preceding_moves=[PrecedingMove(**m) for m in moves[: pos.move_index]],
        # All moves from move_index to the end of the line so the frontend
        # can drive the full alternating user/computer sequence locally.
        remaining_moves=[PrecedingMove(**m) for m in moves[pos.move_index :]],
        is_new=pos.repetitions == 0,
        is_leech=pos.is_leech,
        repetitions=pos.repetitions,
        ease_factor=pos.ease_factor,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/session/start", response_model=SessionStartResponse)
def start_session(
    body: SessionStartRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    seeded = 0
    for lib in _libraries_to_seed(db, user, body.mode, body.scope):
        seeded += ensure_positions_for_library(db, user.id, lib)

    ps = PracticeSession(
        user_id=user.id,
        mode=body.mode,
        scope=json.dumps(body.scope),
        stats=json.dumps({"correct": 0, "wrong": 0, "positions_seen": 0}),
    )
    db.add(ps)
    db.commit()
    db.refresh(ps)

    return SessionStartResponse(
        id=ps.id,
        mode=ps.mode,
        scope=body.scope,
        started_at=ps.started_at,
        seeded_positions=seeded,
    )


@router.get(
    "/session/{sid}/next",
    response_model=Union[NextPositionResponse, SessionDoneResponse],
)
def next_position(
    sid: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    ps = _get_active_session(db, sid, user)
    scope = json.loads(ps.scope or "{}")

    # Loop to skip stale positions (move was deleted from the line).
    for _ in range(50):
        pos = select_next_position(db, user.id, ps.mode, scope)
        if not pos:
            return SessionDoneResponse(stats=json.loads(ps.stats or "{}"))

        line = db.get(Line, pos.line_id)
        if not line:
            db.delete(pos)
            db.commit()
            continue

        moves = json.loads(line.moves or "[]")
        if pos.move_index >= len(moves):
            db.delete(pos)
            db.commit()
            continue

        return _build_next_response(db, pos)

    return SessionDoneResponse(stats=json.loads(ps.stats or "{}"))


@router.post("/session/{sid}/answer", response_model=AnswerResponse)
def submit_answer(
    sid: UUID,
    body: AnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    ps = _get_active_session(db, sid, user)

    pos = db.get(PracticePosition, body.practice_position_id)
    if not pos or pos.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position not found")

    line = db.get(Line, pos.line_id)
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")

    moves = json.loads(line.moves or "[]")
    if pos.move_index >= len(moves):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Move no longer exists in line")

    expected = moves[pos.move_index]
    expected_uci = (expected.get("uci") or "").strip().lower()
    submitted = body.move_uci.strip().lower()

    # Full-line practice sends line_correct to reflect the outcome of the
    # entire mainline sequence (not just this one move), so prefer it when
    # present.  For single-move practice (line_correct is None) we fall back
    # to the direct UCI comparison.
    if body.line_correct is not None:
        was_correct = body.line_correct
    else:
        was_correct = submitted == expected_uci

    if was_correct:
        srs_engine.apply_correct(pos, body.ease)
    else:
        srs_engine.apply_wrong(pos)

    db.add(
        ReviewLog(
            user_id=user.id,
            practice_pos_id=pos.id,
            session_id=ps.id,
            was_correct=was_correct,
            ease_chosen=body.ease if was_correct else None,
            response_ms=body.response_ms,
        )
    )

    # Update session stats
    stats = json.loads(ps.stats or "{}")
    stats["positions_seen"] = stats.get("positions_seen", 0) + 1
    if was_correct:
        stats["correct"] = stats.get("correct", 0) + 1
    else:
        stats["wrong"] = stats.get("wrong", 0) + 1
    ps.stats = json.dumps(stats)

    db.add(pos)
    db.add(ps)
    db.commit()
    db.refresh(pos)

    return AnswerResponse(
        correct=was_correct,
        expected_san=expected.get("san", ""),
        expected_uci=expected.get("uci", ""),
        fen_after=expected.get("fen_after", ""),
        note=expected.get("note"),
        srs=SrsState(
            ease_factor=pos.ease_factor,
            interval_days=pos.interval_days,
            due_at=pos.due_at,
            repetitions=pos.repetitions,
            leech_count=pos.leech_count,
            is_leech=pos.is_leech,
        ),
    )


@router.post("/session/{sid}/end", response_model=SessionEndResponse)
def end_session(
    sid: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    ps = db.get(PracticeSession, sid)
    if not ps or ps.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if not ps.ended_at:
        ps.ended_at = datetime.utcnow()
        db.add(ps)
        db.commit()
        db.refresh(ps)
    return SessionEndResponse(
        id=ps.id,
        ended_at=ps.ended_at,
        stats=json.loads(ps.stats or "{}"),
    )


@router.get("/due-count", response_model=DueCountResponse)
def due_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    now = datetime.utcnow()
    all_pos = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    return DueCountResponse(
        count=sum(1 for p in all_pos if p.due_at <= now),
        new=sum(1 for p in all_pos if p.repetitions == 0),
        leeches=sum(1 for p in all_pos if p.is_leech),
    )
