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
from services.activity_log import log_activity
from schemas.line import (
    LineCreate,
    LineUpdate,
    LineMoveAppend,
    LineMoveNoteUpdate,
    LineMovesBatchImport,
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


def _accessible_library_or_404(session: Session, lib_id: UUID, user: User) -> Library:
    """Allow access to: owner, any admin, or user 'nick'"""
    lib = session.get(Library, lib_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")

    is_owner = lib.owner_user_id == user.id
    is_admin = user.role == "admin"
    is_nick = user.username == "nick"

    if not (is_owner or is_admin or is_nick):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to access this library")
    return lib


def _owned_line_or_404(session: Session, line_id: UUID, user: User) -> Line:
    line = session.get(Line, line_id)
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    lib = session.get(Library, line.library_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")

    is_owner = lib.owner_user_id == user.id
    is_admin = user.role == "admin"
    is_nick = user.username == "nick"

    if not (is_owner or is_admin or is_nick):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to access this line")
    return line


@router.get("/libraries/{lib_id}/lines", response_model=list[LineResponse])
def list_lines(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _accessible_library_or_404(session, lib_id, user)
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
    _accessible_library_or_404(session, lib_id, user)
    existing_count = len(
        session.exec(select(Line).where(Line.library_id == lib_id)).all()
    )
    # Generate default name if not provided
    line_name = body.name or f"Opening Line [{existing_count + 1}]"
    line = Line(
        library_id=lib_id,
        name=line_name,
        starting_fen=body.starting_fen or STARTING_FEN,
        moves="[]",
        order_index=existing_count,
    )
    session.add(line)
    session.commit()
    session.refresh(line)
    lib = session.get(Library, lib_id)
    log_activity(session, user.id, user.username, "create_line", target=line.name, detail=lib.name if lib else None)
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
    line_name = line.name
    lib = session.get(Library, line.library_id)
    from models.practice import PracticePosition
    from models.line import MoveNote

    # Delete related practice positions
    positions = session.exec(select(PracticePosition).where(PracticePosition.line_id == line_id)).all()
    for pos in positions:
        session.delete(pos)

    # Delete related move notes
    notes = session.exec(select(MoveNote).where(MoveNote.line_id == line_id)).all()
    for note in notes:
        session.delete(note)

    # Delete the line
    session.delete(line)
    session.commit()
    log_activity(session, user.id, user.username, "delete_line", target=line_name, detail=lib.name if lib else None)


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


@router.post("/lines/{line_id}/duplicate", response_model=LineResponse, status_code=status.HTTP_201_CREATED)
def duplicate_line(
    line_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    src = _owned_line_or_404(session, line_id, user)

    existing = session.exec(select(Line).where(Line.library_id == src.library_id)).all()
    new_name = f"{src.name} copy" if src.name else "Unnamed copy"

    copy = Line(
        library_id=src.library_id,
        name=new_name,
        starting_fen=src.starting_fen,
        moves=src.moves,
        order_index=len(existing),
    )
    session.add(copy)
    session.commit()
    session.refresh(copy)
    return copy


@router.put("/lines/{line_id}/moves", response_model=LineResponse)
def replace_moves(
    line_id: UUID,
    body: LineMovesBatchImport,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    line = _owned_line_or_404(session, line_id, user)

    # Use provided starting FEN or keep the line's existing one
    start_fen = body.starting_fen or line.starting_fen
    board = chess.Board(start_fen)
    new_moves = []

    # Validate and build move records
    for san in body.moves:
        try:
            move = board.parse_san(san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid SAN '{san}': {exc}")
        uci = move.uci()
        board.push(move)
        fen_after = board.fen()
        new_moves.append({"san": san, "uci": uci, "fen_after": fen_after})

    # Update line
    if body.starting_fen:
        line.starting_fen = body.starting_fen
    line.moves = json.dumps(new_moves)
    line.updated_at = datetime.utcnow()
    session.add(line)
    session.commit()
    session.refresh(line)
    return line
