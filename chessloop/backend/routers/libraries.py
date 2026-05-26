from datetime import datetime
from uuid import UUID
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
import chess

from database import get_session
from models import User, Library, Line, PracticePosition, ReviewLog
from auth.dependencies import get_current_user
from schemas.library import (
    LibraryCreate,
    LibraryUpdate,
    LibraryActiveToggle,
    LibraryResponse,
    ConflictResponse,
    EvaluateConflictsResult,
)
from services import opening_import

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _owned_or_404(session: Session, lib_id: UUID, user: User) -> Library:
    lib = session.get(Library, lib_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")
    if lib.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")
    return lib


class LichessImportResult(BaseModel):
    library_name: str
    eco_code: str
    imported: int
    skipped: int
    errors: list[str]


@router.get("", response_model=list[LibraryResponse])
def list_libraries(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(Library).where(Library.owner_user_id == user.id)).all()


@router.post("", response_model=LibraryResponse, status_code=status.HTTP_201_CREATED)
def create_library(
    body: LibraryCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = Library(owner_user_id=user.id, **body.model_dump())
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return lib


@router.get("/{lib_id}", response_model=LibraryResponse)
def get_library(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _owned_or_404(session, lib_id, user)


@router.put("/{lib_id}", response_model=LibraryResponse)
def update_library(
    lib_id: UUID,
    body: LibraryUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)

    # If renaming, check for duplicates first
    if "name" in body.model_dump(exclude_unset=True):
        new_name = body.name
        existing = session.exec(
            select(Library).where(
                Library.owner_user_id == user.id,
                Library.name == new_name,
                Library.id != lib_id,
            )
        ).first()
        if existing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Library name '{new_name}' already exists in your account"
            )

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(lib, k, v)
    lib.updated_at = datetime.utcnow()
    session.add(lib)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        if "uq_owner_library_name" in str(e):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Library name '{lib.name}' already exists in your account"
            )
        raise
    session.refresh(lib)
    return lib


@router.delete("/{lib_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)

    # Get all lines in this library
    lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()
    line_ids = [line.id for line in lines]

    if line_ids:
        # Get all practice positions for these lines
        practice_positions = session.exec(
            select(PracticePosition).where(PracticePosition.line_id.in_(line_ids))
        ).all()
        pp_ids = [pp.id for pp in practice_positions]

        # Delete review logs that reference these practice positions
        if pp_ids:
            review_logs = session.exec(
                select(ReviewLog).where(ReviewLog.practice_pos_id.in_(pp_ids))
            ).all()
            for rl in review_logs:
                session.delete(rl)
            session.flush()  # Execute all review log deletes before continuing

        # Delete practice positions
        for pp in practice_positions:
            session.delete(pp)
        session.flush()  # Execute all practice position deletes before deleting lines

    # Delete lines
    for line in lines:
        session.delete(line)
    session.flush()  # Execute all line deletes before deleting library

    # Delete library
    session.delete(lib)
    session.commit()


@router.patch("/{lib_id}/active", response_model=LibraryResponse)
def set_active(
    lib_id: UUID,
    body: LibraryActiveToggle,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)
    lib.is_active = body.is_active
    lib.updated_at = datetime.utcnow()
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return lib


@router.post("/{lib_id}/publish", response_model=LibraryResponse)
def publish(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = session.get(Library, lib_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")

    # Allow: owner, any admin, or the user 'nick'
    is_owner = lib.owner_user_id == user.id
    is_admin = user.role == "admin"
    is_nick = user.username == "nick"

    if not (is_owner or is_admin or is_nick):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owner, admins, or nick can publish libraries")

    lib.is_public = True
    lib.published_at = datetime.utcnow()
    lib.updated_at = lib.published_at
    session.add(lib)
    session.commit()
    session.refresh(lib)
    return lib


@router.post("/{lib_id}/fork", response_model=LibraryResponse, status_code=status.HTTP_201_CREATED)
def fork(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    source = session.get(Library, lib_id)
    if not source:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")
    if not source.is_public and source.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Library is private")

    forked = Library(
        name=f"{source.name} (fork)",
        color=source.color,
        owner_user_id=user.id,
        forked_from_id=source.id,
        description=source.description,
        eco_code=source.eco_code,
        difficulty=source.difficulty,
    )
    session.add(forked)
    session.commit()
    session.refresh(forked)

    for src_line in session.exec(select(Line).where(Line.library_id == source.id)).all():
        session.add(Line(
            library_id=forked.id,
            name=src_line.name,
            starting_fen=src_line.starting_fen,
            moves=src_line.moves,
            order_index=src_line.order_index,
        ))
    session.commit()
    return forked


@router.get("/{lib_id}/export/pgn")
def export_library_pgn(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = _owned_or_404(session, lib_id, user)
    lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()

    pgn_content = ""
    for line in lines:
        pgn_content += f'[Event "{lib.name}"]\n'
        if line.name:
            pgn_content += f'[OpeningName "{line.name}"]\n'
        if lib.eco_code:
            pgn_content += f'[ECO "{lib.eco_code}"]\n'
        pgn_content += f'[White "ChessLoop"]\n'
        pgn_content += f'[Black "ChessLoop"]\n'
        pgn_content += '\n'

        moves = json.loads(line.moves)
        for i, move in enumerate(moves):
            if i % 2 == 0:
                pgn_content += f'{(i // 2) + 1}. '
            pgn_content += move['san']
            if i < len(moves) - 1:
                pgn_content += ' '
        pgn_content += '\n\n'

    def generate():
        yield pgn_content

    filename = f"{lib.name.replace(' ', '_')}.pgn"
    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/{lib_id}/import-from-lichess", response_model=LichessImportResult)
def import_from_lichess(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Import opening lines from Lichess into a user's own library by ECO code."""
    lib = _owned_or_404(session, lib_id, user)

    if lib.is_public:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Use the admin panel to import into public libraries",
        )

    if not lib.eco_code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Library must have an ECO code set to import from Lichess",
        )

    try:
        result = opening_import.import_lichess_lines_into_library(lib_id, lib.eco_code, session)
        return LichessImportResult(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Import failed: {e}")


@router.get("/{lib_id}/conflicts", response_model=EvaluateConflictsResult)
def evaluate_conflicts(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Find positions where opening lines in a library have different follow-on moves."""
    lib = _owned_or_404(session, lib_id, user)

    # Get all lines in the library
    lines = session.exec(select(Line).where(Line.library_id == lib_id).order_by(Line.order_index)).all()

    # Build position map: (position_hash, side_to_move) -> [(line_name, line_id, move_number, next_move)]
    # Key includes color to move so we only compare positions from the same perspective
    position_map = {}

    for line in lines:
        try:
            moves = json.loads(line.moves) if isinstance(line.moves, str) else line.moves
            if not moves:
                continue

            board = chess.Board(line.starting_fen)

            # Record starting position
            fen_key = board.fen().split()[0]  # piece positions only
            side_key = 'w' if board.turn else 'b'  # whose turn it is
            position_key = (fen_key, side_key)
            if position_key not in position_map:
                position_map[position_key] = []

            # Process each move
            for move_index, move_obj in enumerate(moves):
                san = move_obj.get('san', '')
                try:
                    move = board.push_san(san)

                    # After this move, record what position we're at and what the next move would be
                    fen_key = board.fen().split()[0]  # piece positions only
                    side_key = 'w' if board.turn else 'b'  # whose turn it will be for the next move
                    position_key = (fen_key, side_key)
                    if position_key not in position_map:
                        position_map[position_key] = []

                    # If there's a next move, record it as the follow-on
                    if move_index + 1 < len(moves):
                        next_move_san = moves[move_index + 1].get('san', '')
                        position_map[position_key].append({
                            'line_name': line.name or f"Line {line.order_index}",
                            'line_id': str(line.id),
                            'move_number': move_index + 1,
                            'next_move': next_move_san,
                            'fen': board.fen()
                        })
                except Exception:
                    # Skip invalid moves
                    continue

        except Exception:
            # Skip lines with parsing errors
            continue

    # Find conflicts: positions with different follow-on moves (same position, same color to move)
    conflicts = []
    for position_key, entries in position_map.items():
        if len(entries) > 1:
            # Check all pairs for different next moves
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    entry_a = entries[i]
                    entry_b = entries[j]
                    if entry_a['next_move'] != entry_b['next_move']:
                        conflicts.append(ConflictResponse(
                            line_a_name=entry_a['line_name'],
                            line_b_name=entry_b['line_name'],
                            move_number=entry_a['move_number'],
                            next_move_a=entry_a['next_move'],
                            next_move_b=entry_b['next_move'],
                            position_fen=entry_a['fen']
                        ))

    return EvaluateConflictsResult(
        total_positions=len(position_map),
        conflicts_found=len(conflicts),
        conflicts=conflicts
    )
