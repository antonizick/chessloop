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
from models.library_video_link import LibraryVideoLink
from auth.dependencies import get_current_user
from schemas.library import (
    LibraryCreate,
    LibraryUpdate,
    LibraryActiveToggle,
    LibraryResponse,
    ConflictResponse,
    EvaluateConflictsResult,
)
from schemas.library_video_link import VideoLinkCreate, VideoLinkResponse
from services import opening_import

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _owned_or_404(session: Session, lib_id: UUID, user: User) -> Library:
    lib = session.exec(
        select(Library).where(Library.id == lib_id)
    ).first()
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
    current_fen: str = None,
    current_line_id: str = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Find all lines that share the current position and show their next moves."""
    lib = _owned_or_404(session, lib_id, user)

    # Get all lines in the library
    lines = session.exec(select(Line).where(Line.library_id == lib_id).order_by(Line.order_index)).all()

    if not current_fen:
        # If no position specified, use the starting FEN
        if lines:
            current_fen = lines[0].starting_fen
        else:
            return EvaluateConflictsResult(total_positions=0, conflicts_found=0, conflicts=[])

    # Extract just the piece placement from the FEN (ignore turn, castling, etc.)
    current_position_key = current_fen.split()[0]
    # Also get whose turn it is
    current_turn = current_fen.split()[1] if len(current_fen.split()) > 1 else 'w'

    # Find the next move in the current line at this position
    current_line_next_move = None
    current_line_name = None

    if current_line_id:
        current_line = session.get(Line, UUID(current_line_id))
        if current_line:
            current_line_name = current_line.name or f"Line {current_line.order_index}"
            try:
                moves = json.loads(current_line.moves) if isinstance(current_line.moves, str) else current_line.moves
                board = chess.Board(current_line.starting_fen)

                # Check starting position
                board_position_key = board.fen().split()[0]
                board_turn = board.fen().split()[1] if len(board.fen().split()) > 1 else 'w'

                if board_position_key == current_position_key and board_turn == current_turn:
                    # This line starts at our position
                    if moves:
                        current_line_next_move = moves[0].get('san', '')
                else:
                    # Look for the position later in the line
                    for move_index, move_obj in enumerate(moves):
                        san = move_obj.get('san', '')
                        try:
                            board.push_san(san)
                            board_position_key = board.fen().split()[0]
                            board_turn = board.fen().split()[1] if len(board.fen().split()) > 1 else 'w'

                            if board_position_key == current_position_key and board_turn == current_turn:
                                if move_index + 1 < len(moves):
                                    current_line_next_move = moves[move_index + 1].get('san', '')
                                break
                        except Exception:
                            continue
            except Exception:
                pass

    # Find all lines that contain this position and what they play next
    other_lines_by_move = {}  # next_move -> [line_name, line_id]

    for line in lines:
        # Skip the current line
        if current_line_id and str(line.id) == current_line_id:
            continue

        try:
            moves = json.loads(line.moves) if isinstance(line.moves, str) else line.moves
            if not moves:
                continue

            board = chess.Board(line.starting_fen)

            # Check starting position
            board_position_key = board.fen().split()[0]
            board_turn = board.fen().split()[1] if len(board.fen().split()) > 1 else 'w'

            if board_position_key == current_position_key and board_turn == current_turn:
                # This line starts at our position, next move is the first move
                if len(moves) > 0:
                    next_move = moves[0].get('san', '')
                    if next_move:
                        if next_move not in other_lines_by_move:
                            other_lines_by_move[next_move] = []
                        other_lines_by_move[next_move].append({
                            'line_name': line.name or f"Line {line.order_index}",
                            'line_id': str(line.id)
                        })
                continue

            # Process each move to find if this position appears later
            for move_index, move_obj in enumerate(moves):
                san = move_obj.get('san', '')
                try:
                    board.push_san(san)

                    # Check if we're at the target position
                    board_position_key = board.fen().split()[0]
                    board_turn = board.fen().split()[1] if len(board.fen().split()) > 1 else 'w'

                    if board_position_key == current_position_key and board_turn == current_turn:
                        # Found the position, get the next move if it exists
                        if move_index + 1 < len(moves):
                            next_move = moves[move_index + 1].get('san', '')
                            if next_move:
                                if next_move not in other_lines_by_move:
                                    other_lines_by_move[next_move] = []
                                other_lines_by_move[next_move].append({
                                    'line_name': line.name or f"Line {line.order_index}",
                                    'line_id': str(line.id)
                                })
                        break

                except Exception:
                    # Skip invalid moves
                    continue

        except Exception:
            # Skip lines with parsing errors
            continue

    # Create conflict entries: current line vs other lines with different moves
    conflicts = []

    if current_line_next_move and current_line_name:
        # Look for other lines with different next moves
        for other_move, other_lines in other_lines_by_move.items():
            if other_move != current_line_next_move:
                # Create a conflict for each line with a different move
                for other_line in other_lines:
                    conflicts.append(ConflictResponse(
                        line_a_name=current_line_name,
                        line_b_name=other_line['line_name'],
                        move_number=chess.Board(current_fen).fullmove_number,
                        turn_color='white' if current_turn == 'w' else 'black',
                        next_move_a=current_line_next_move,
                        next_move_b=other_move,
                        position_fen=current_fen
                    ))

    return EvaluateConflictsResult(
        total_positions=1,
        conflicts_found=len(conflicts),
        conflicts=conflicts
    )


# ── Video Links ───────────────────────────────────────────────────────────────

@router.get("/{lib_id}/video-links", response_model=list[VideoLinkResponse])
def list_video_links(
    lib_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    lib = session.exec(
        select(Library).where(Library.id == lib_id)
    ).first()
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")
    if not lib.is_public and lib.owner_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
    return session.exec(
        select(LibraryVideoLink).where(LibraryVideoLink.library_id == lib_id)
    ).all()


@router.post("/{lib_id}/video-links", response_model=VideoLinkResponse, status_code=status.HTTP_201_CREATED)
def add_video_link(
    lib_id: UUID,
    body: VideoLinkCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _owned_or_404(session, lib_id, user)
    count = len(session.exec(
        select(LibraryVideoLink).where(LibraryVideoLink.library_id == lib_id)
    ).all())
    if count >= 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Maximum of 10 video links per library")
    link = LibraryVideoLink(library_id=lib_id, title=body.title, url=body.url)
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


@router.delete("/{lib_id}/video-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video_link(
    lib_id: UUID,
    link_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _owned_or_404(session, lib_id, user)
    # Verify link exists and belongs to this library
    all_links = session.exec(
        select(LibraryVideoLink).where(LibraryVideoLink.library_id == lib_id)
    ).all()
    if not any(str(l.id) == str(link_id) for l in all_links):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video link not found")
    # Use raw SQL delete to avoid SQLAlchemy session tracking issues
    from sqlalchemy import text
    stmt = text("DELETE FROM library_video_link WHERE id = :link_id").bindparams(link_id=str(link_id))
    session.exec(stmt)
    session.commit()
