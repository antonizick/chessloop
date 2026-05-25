import json
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
import chess

from database import get_session
from models import User, Library, Line
from models.line import STARTING_FEN
from auth.dependencies import get_current_user
from schemas.line import (
    LineCreate,
    LineUpdate,
    LineMoveAppend,
    LineMoveNoteUpdate,
    LineResponse,
)

router = APIRouter(tags=["lines"])


def _owned_library_or_404(session: Session, lib_id: UUID, user: User) -> Library:
    lib = session.get(Library, lib_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")
    if lib.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")
    return lib


def _owned_line_or_404(session: Session, line_id: UUID, user: User) -> Line:
    line = session.get(Line, line_id)
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    lib = session.get(Library, line.library_id)
    if not lib or lib.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")
    return line


@router.get("/libraries/{lib_id}/lines", response_model=list[LineResponse])
def list_lines(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _owned_library_or_404(session, lib_id, user)
    return session.exec(
        select(Line).where(Line.library_id == lib_id).order_by(Line.order_index)
    ).all()


@router.post(
    "/libraries/{lib_id}/lines",
    response_model=LineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_line(
    lib_id: UUID,
    body: LineCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _owned_library_or_404(session, lib_id, user)
    existing_count = len(
        session.exec(select(Line).where(Line.library_id == lib_id)).all()
    )
    line = Line(
        library_id=lib_id,
        name=body.name,
        starting_fen=body.starting_fen or STARTING_FEN,
        moves="[]",
        order_index=existing_count,
    )
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


@router.get("/lines/{line_id}", response_model=LineResponse)
def get_line(
    line_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _owned_line_or_404(session, line_id, user)


@router.put("/lines/{line_id}", response_model=LineResponse)
def update_line(
    line_id: UUID,
    body: LineUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    line = _owned_line_or_404(session, line_id, user)
    if body.name is not None:
        line.name = body.name
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


@router.delete("/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line(
    line_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    line = _owned_line_or_404(session, line_id, user)
    session.delete(line)
    session.commit()


def _canonical_fen(fen: str) -> str:
    """Strip move counters from FEN for use as a position key."""
    parts = fen.split()
    return " ".join(parts[:4])


@router.post("/lines/{line_id}/moves", response_model=LineResponse)
def append_move(
    line_id: UUID,
    body: LineMoveAppend,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    line = _owned_line_or_404(session, line_id, user)
    moves = json.loads(line.moves or "[]")

    # If uci / fen_after are missing, compute them with python-chess.
    if body.uci is None or body.fen_after is None:
        board = chess.Board(line.starting_fen)
        for m in moves:
            board.push_san(m["san"])
        try:
            move = board.parse_san(body.san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid SAN '{body.san}': {exc}")
        uci = move.uci()
        board.push(move)
        fen_after = board.fen()
    else:
        uci = body.uci
        fen_after = body.fen_after

    move_record = {"san": body.san, "uci": uci, "fen_after": fen_after}
    if body.note:
        move_record["note"] = body.note

    moves.append(move_record)
    line.moves = json.dumps(moves)
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


@router.delete("/lines/{line_id}/moves/{index}", response_model=LineResponse)
def delete_move(
    line_id: UUID,
    index: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    line = _owned_line_or_404(session, line_id, user)
    moves = json.loads(line.moves or "[]")
    if index < 0 or index >= len(moves):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Move index out of range")
    del moves[index:]  # delete this move and everything after — keep line valid
    line.moves = json.dumps(moves)
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


@router.put("/lines/{line_id}/moves/{index}/note", response_model=LineResponse)
def update_move_note(
    line_id: UUID,
    index: int,
    body: LineMoveNoteUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    line = _owned_line_or_404(session, line_id, user)
    moves = json.loads(line.moves or "[]")
    if index < 0 or index >= len(moves):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Move index out of range")
    moves[index]["note"] = body.text
    line.moves = json.dumps(moves)
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    session.refresh(line)
    return line
