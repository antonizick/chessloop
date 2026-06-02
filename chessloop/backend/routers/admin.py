"""Admin router — backup management + user management + opening import. Requires role='admin'."""

from uuid import UUID
from typing import Optional
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from database import get_session
from models import Backup, Library
from models.user import User
from models.practice import PracticePosition, ReviewLog, PracticeSession
from auth.dependencies import get_current_user
from auth.password import hash_password
from services import backup_service
from services import opening_import

# Special user ID for seeded opening libraries (so they don't appear in admin's account)
SEEDBOT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


# ── Users ─────────────────────────────────────────────────────────────────────


class UserAdminResponse(BaseModel):
    id: UUID
    username: str
    email: str
    role: str
    mfa_enabled: bool
    created_at: str
    last_login: str | None

    class Config:
        from_attributes = True


class PatchUserRoleRequest(BaseModel):
    role: str  # 'user' | 'admin'


class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: str = "user"


class UpdateUserRequest(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    role: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/users", response_model=list[UserAdminResponse])
def list_users(
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    users = session.exec(select(User).where(User.id != SEEDBOT_USER_ID).order_by(User.created_at)).all()  # type: ignore[arg-type]
    return [
        UserAdminResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            mfa_enabled=u.mfa_enabled,
            created_at=u.created_at.isoformat(),
            last_login=u.last_login.isoformat() if u.last_login else None,
        )
        for u in users
    ]


@router.post("/users", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    if body.role not in ("user", "admin"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role must be 'user' or 'admin'")

    # Collision check: email or username already exists
    existing = session.exec(
        select(User).where((User.email == body.email) | (User.username == body.username))
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already exists")

    # Create user with hashed password
    user = User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return UserAdminResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at.isoformat(),
        last_login=user.last_login.isoformat() if user.last_login else None,
    )


@router.patch("/users/{user_id}", response_model=UserAdminResponse)
def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    # Protect seedbot from modification
    if user_id == SEEDBOT_USER_ID:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot modify the seedbot account")

    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Check for email/username collision (if changing either)
    if body.email or body.username:
        collision = session.exec(
            select(User).where(
                (User.id != user_id) & ((User.email == body.email) | (User.username == body.username))
            )
        ).first()
        if collision:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already exists")

    # Apply updates
    if body.email:
        target.email = body.email
    if body.username:
        target.username = body.username
    if body.role:
        if body.role not in ("user", "admin"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role must be 'user' or 'admin'")
        if target.id == admin.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change your own role")
        target.role = body.role
    if body.new_password:
        target.password_hash = hash_password(body.new_password)

    session.add(target)
    session.commit()
    session.refresh(target)

    return UserAdminResponse(
        id=target.id,
        username=target.username,
        email=target.email,
        role=target.role,
        mfa_enabled=target.mfa_enabled,
        created_at=target.created_at.isoformat(),
        last_login=target.last_login.isoformat() if target.last_login else None,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    # Protect seedbot from deletion
    if user_id == SEEDBOT_USER_ID:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot delete the seedbot account")

    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")

    # Cascade delete: review logs, practice positions, sessions, lines, libraries, signals, backups
    from models.line import Line
    from models.public_signal import PublicSignal

    # Delete review logs
    review_logs = session.exec(select(ReviewLog).where(ReviewLog.user_id == user_id)).all()
    for log in review_logs:
        session.delete(log)

    # Delete practice positions
    practice_positions = session.exec(select(PracticePosition).where(PracticePosition.user_id == user_id)).all()
    for pos in practice_positions:
        session.delete(pos)

    # Delete practice sessions
    practice_sessions = session.exec(select(PracticeSession).where(PracticeSession.user_id == user_id)).all()
    for sess in practice_sessions:
        session.delete(sess)

    # Delete lines and libraries owned by this user
    libraries = session.exec(select(Library).where(Library.owner_user_id == user_id)).all()
    for lib in libraries:
        lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()
        for line in lines:
            session.delete(line)
        session.delete(lib)

    # Delete public signals (stars, comments)
    public_signals = session.exec(select(PublicSignal).where(PublicSignal.user_id == user_id)).all()
    for signal in public_signals:
        session.delete(signal)

    # Delete backups created by this user
    from pathlib import Path
    backups = session.exec(select(Backup).where(Backup.created_by == user_id)).all()
    for backup in backups:
        p = Path(backup.file_path)
        if p.exists():
            p.unlink()
        session.delete(backup)

    # Finally delete the user
    session.delete(target)
    session.commit()


# ── Backups ───────────────────────────────────────────────────────────────────


class BackupResponse(BaseModel):
    id: UUID
    name: str
    type: str
    size_bytes: int
    created_by: UUID
    created_at: str


class CreateBackupRequest(BaseModel):
    name: str
    type: str  # 'full' | 'content' | 'progress'


@router.get("/backups", response_model=list[BackupResponse])
def list_backups(
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    backups = session.exec(
        select(Backup).order_by(Backup.created_at.desc())  # type: ignore[arg-type]
    ).all()
    return [
        BackupResponse(
            id=b.id,
            name=b.name,
            type=b.type,
            size_bytes=b.size_bytes,
            created_at=b.created_at.isoformat(),
            created_by=b.created_by,
        )
        for b in backups
    ]


@router.post("/backups", response_model=BackupResponse, status_code=status.HTTP_201_CREATED)
def create_backup(
    body: CreateBackupRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    if body.type not in ("full", "content", "progress"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "type must be full, content, or progress")
    try:
        backup = backup_service.create_backup(session, body.name, body.type, admin.id)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))
    return BackupResponse(
        id=backup.id,
        name=backup.name,
        type=backup.type,
        size_bytes=backup.size_bytes,
        created_at=backup.created_at.isoformat(),
        created_by=backup.created_by,
    )


@router.post("/backups/upload", response_model=BackupResponse, status_code=status.HTTP_201_CREATED)
def upload_backup(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    type: Optional[str] = Form("full"),
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """
    Upload a previously-downloaded backup file to recover the system.
    Validates the file is a valid SQLite database, saves it, and registers it.
    """
    if type not in ("full", "content", "progress"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "type must be full, content, or progress")

    # Read file bytes
    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    # Validate SQLite magic bytes: "SQLite format 3\x00"
    if not file_bytes.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid SQLite database file")

    # Generate backup filename with timestamp
    backup_name = name or Path(file.filename or "uploaded-backup").stem
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{type}_{ts}_{backup_name[:40].replace(' ', '_')}.db"

    # Save file to backup directory
    backup_dir = Path(backup_service.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / filename

    try:
        with open(dest, "wb") as f:
            f.write(file_bytes)
    except IOError as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to save backup: {e}")

    size = dest.stat().st_size

    # Create backup record
    backup = Backup(
        name=backup_name,
        type=type,
        file_path=str(dest),
        size_bytes=size,
        created_by=admin.id,
        created_at=datetime.utcnow(),
    )
    session.add(backup)
    session.commit()
    session.refresh(backup)

    # Prune oldest backups if over limit
    backup_service._prune(session)

    return BackupResponse(
        id=backup.id,
        name=backup.name,
        type=backup.type,
        size_bytes=backup.size_bytes,
        created_at=backup.created_at.isoformat(),
        created_by=backup.created_by,
    )


@router.get("/backups/{backup_id}/download")
def download_backup(
    backup_id: UUID,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    backup = session.get(Backup, backup_id)
    if not backup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")
    path = backup_service.get_backup_path(backup)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup file missing on disk")
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=path.name,
    )


@router.post("/backups/{backup_id}/restore", status_code=status.HTTP_200_OK)
def restore_backup(
    backup_id: UUID,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    backup = session.get(Backup, backup_id)
    if not backup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")
    path = backup_service.get_backup_path(backup)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup file missing on disk")
    try:
        backup_service.restore_backup(backup)
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Restore failed: {e}")
    return {"status": "restored", "name": backup.name, "message": "Restore complete. Reload the page to see updated data."}


@router.delete("/backups/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(
    backup_id: UUID,
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    backup = session.get(Backup, backup_id)
    if not backup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found")
    backup_service.delete_backup(session, backup)


# ── Opening import (admin) ────────────────────────────────────────────────────


class OpeningSearchResult(BaseModel):
    eco: str
    name: str
    color: str
    difficulty: str
    description: str
    moves: list[str]
    available_variations: int


class SeedOpeningsResponse(BaseModel):
    seeded: int
    skipped: int
    errors: list[str]


class ImportOpeningRequest(BaseModel):
    eco: str
    name: str
    color: str
    difficulty: str
    description: str
    moves: list[str]
    publish: bool = False
    variations_to_import: int = 0


class ImportOpeningResponse(BaseModel):
    id: str
    name: str
    status: str  # 'created' | 'exists'


class PullVariationsRequest(BaseModel):
    library_id: UUID
    count: int = 5


class PullVariationsResponse(BaseModel):
    opening_name: str
    added: int
    message: str


@router.get("/openings/search", response_model=list[OpeningSearchResult])
def search_openings(
    q: str = Query(default="", description="Search by opening name or ECO code"),
    _: User = Depends(require_admin),
):
    """Search the bundled ECO opening database. Returns up to 20 results."""
    results = opening_import.search_openings(q)
    return [
        OpeningSearchResult(
            eco=r["eco"],
            name=r["name"],
            color=r["color"],
            difficulty=r["difficulty"],
            description=r["description"],
            moves=r["moves"],
            available_variations=opening_import.count_lichess_variations(r["moves"]),
        )
        for r in results
    ]


@router.post("/openings/seed", response_model=SeedOpeningsResponse)
def seed_openings(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Seed all 16 standard starter opening libraries to public discovery.
    Libraries are owned by a special seedbot user, not the admin's account.
    Already-existing libraries are skipped. New ones are published automatically.
    """
    # Ensure seedbot user exists
    seedbot = session.get(User, SEEDBOT_USER_ID)
    if not seedbot:
        try:
            seedbot = User(
                id=SEEDBOT_USER_ID,
                username="seedbot",
                email="seedbot@chessloop.local",
                password_hash="",  # No password
                role="user",
            )
            session.add(seedbot)
            session.commit()
        except Exception as e:
            # User may already exist or there's a unique constraint issue
            session.rollback()
            seedbot = session.get(User, SEEDBOT_USER_ID)
            if not seedbot:
                # Try to create with unique email and username if they're taken
                try:
                    import uuid
                    unique_id = str(uuid.uuid4())[:8]
                    seedbot = User(
                        id=SEEDBOT_USER_ID,
                        username=f"seedbot-{unique_id}",
                        email=f"seedbot-{unique_id}@chessloop.local",
                        password_hash="",
                        role="user",
                    )
                    session.add(seedbot)
                    session.commit()
                except Exception as e2:
                    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to create seedbot user: {e2}")

    seeded = 0
    skipped = 0
    errors: list[str] = []

    for eco_code, opening_name, initial_moves, color, difficulty in opening_import.STARTER_OPENINGS:
        try:
            entry = next(
                (e for e in opening_import.ECO_DATABASE if e["name"] == opening_name),
                None,
            )
            description = entry["description"] if entry else f"ECO {eco_code} — starter opening."
            moves = entry["moves"] if entry else initial_moves

            lib, status_str = opening_import.import_opening(
                eco=eco_code,
                name=opening_name,
                color=color,
                difficulty=difficulty,
                description=description,
                moves=moves,
                user_id=admin.id,
                session=session,
                owner_user_id=SEEDBOT_USER_ID,
            )

            if status_str == "created":
                try:
                    opening_import.publish_library(lib.id, session)
                    seeded += 1
                except Exception as pub_err:
                    errors.append(f"{opening_name}: Failed to publish - {pub_err}")
            else:
                skipped += 1

        except Exception as e:
            errors.append(f"{opening_name}: {e}")

    return SeedOpeningsResponse(seeded=seeded, skipped=skipped, errors=errors)


@router.post("/openings/import", response_model=ImportOpeningResponse)
def import_opening(
    body: ImportOpeningRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Import a specific opening (by ECO/name/moves) into the admin's library.
    Optionally publishes immediately and imports additional variations.
    When publishing to public libraries, uses SEEDBOT_USER_ID as owner.
    """
    import json
    import chess

    # Use SEEDBOT_USER_ID as owner when publishing to public libraries
    owner_user_id = SEEDBOT_USER_ID if body.publish else None

    try:
        lib, status_str = opening_import.import_opening(
            eco=body.eco,
            name=body.name,
            color=body.color,
            difficulty=body.difficulty,
            description=body.description,
            moves=body.moves,
            user_id=admin.id,
            session=session,
            owner_user_id=owner_user_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    # Fetch and create variations if requested
    if body.variations_to_import > 0 and status_str == "created":
        variations = opening_import.fetch_lichess_variations(body.moves, body.variations_to_import)
        if variations:
            from models.line import Line, STARTING_FEN
            for i, var_moves in enumerate(variations):
                line_name = f"Variation {i + 2}"  # Main line is 1, variations start at 2
                # Validate and build moves JSON
                board = chess.Board()
                parsed_moves = []
                for san in var_moves:
                    try:
                        move = board.parse_san(san)
                        uci = move.uci()
                        board.push(move)
                        parsed_moves.append((san, uci, board.fen()))
                    except:
                        break
                if parsed_moves:
                    moves_json = json.dumps([
                        {"san": san, "uci": uci, "fen_after": fen_after}
                        for san, uci, fen_after in parsed_moves
                    ])
                    line = Line(
                        library_id=lib.id,
                        name=line_name,
                        starting_fen=STARTING_FEN,
                        moves=moves_json,
                        order_index=i + 1,
                    )
                    session.add(line)
            session.commit()

    if body.publish and status_str == "created":
        opening_import.publish_library(lib.id, session)

    return ImportOpeningResponse(id=str(lib.id), name=lib.name, status=status_str)


@router.post("/openings/pull-variations", response_model=PullVariationsResponse)
def pull_variations(
    body: PullVariationsRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Pull additional variations from the ECO database for an existing opening.
    Looks up the opening by name, finds related ECO entries, and adds them as
    new lines to the existing library.
    """
    from models.library import Library as LibModel
    from models.line import Line, STARTING_FEN
    import json, chess

    # Find the library by ID
    lib = session.get(LibModel, body.library_id)
    if not lib:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Library not found"
        )

    # Find related ECO entries (same base name or ECO prefix)
    base_name = lib.name.split(" — ")[0].lower()
    related = [
        e for e in opening_import.ECO_DATABASE
        if (
            base_name in e["name"].lower()
            or (lib.eco_code and e["eco"].startswith(lib.eco_code[0]))
        )
        and e["name"] != lib.name  # skip main entry itself
    ][:body.count]

    if not related:
        return PullVariationsResponse(
            opening_name=lib.name,
            added=0,
            message="No additional variations found in the ECO database for this opening.",
        )

    # Count existing lines to avoid duplicates
    existing_lines = session.exec(
        select(Line).where(Line.library_id == lib.id)
    ).all()
    existing_names = {line.name for line in existing_lines}
    next_idx = len(existing_lines)

    added = 0
    for entry in related:
        line_name = entry["name"]
        if line_name in existing_names:
            continue

        # Validate + build moves JSON
        board = chess.Board()
        parsed: list[dict] = []
        valid = True
        for san in entry["moves"]:
            try:
                move = board.parse_san(san)
                uci = move.uci()
                board.push(move)
                parsed.append({"san": san, "uci": uci, "fen_after": board.fen()})
            except Exception:
                valid = False
                break

        if not valid or not parsed:
            continue

        new_line = Line(
            library_id=lib.id,
            name=line_name,
            starting_fen=STARTING_FEN,
            moves=json.dumps(parsed),
            order_index=next_idx + added,
        )
        session.add(new_line)
        added += 1

    if added:
        session.commit()

    return PullVariationsResponse(
        opening_name=lib.name,
        added=added,
        message=f"Added {added} variation(s) to '{lib.name}'." if added
                else "All found variations already exist in this library.",
    )


class DeleteOpeningRequest(BaseModel):
    library_id: UUID


class DeleteOpeningResponse(BaseModel):
    deleted: bool
    message: str


class LichessImportRequest(BaseModel):
    library_id: UUID


class LichessImportResponse(BaseModel):
    library_name: str
    eco_code: str
    imported: int
    skipped: int
    errors: list[str]


@router.delete("/openings/delete", response_model=DeleteOpeningResponse, status_code=status.HTTP_200_OK)
def delete_opening(
    name: str = Query(...),
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Delete a public opening library by name.
    Only admins can delete openings. The library must be public.
    Cascades: deletes all lines, practice positions, move notes, and public signals.
    """
    lib = session.exec(
        select(Library).where(
            Library.name == name,
            Library.is_public == True,  # noqa: E712
        )
    ).first()

    if not lib or not lib.is_public:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Public opening not found"
        )

    # Delete all related data
    from models import Line, ReviewLog
    from models.practice import PracticePosition
    from models.public_signal import PublicSignal

    # Delete practice positions and lines for this library
    lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()
    line_ids = [line.id for line in lines]

    if line_ids:
        # Get all practice positions for these lines
        positions = session.exec(
            select(PracticePosition).where(PracticePosition.line_id.in_(line_ids))
        ).all()
        pos_ids = [pos.id for pos in positions]

        # Delete review logs that reference these practice positions
        if pos_ids:
            review_logs = session.exec(
                select(ReviewLog).where(ReviewLog.practice_pos_id.in_(pos_ids))
            ).all()
            for rl in review_logs:
                session.delete(rl)
            session.flush()  # Execute all review log deletes before continuing

        # Delete practice positions
        for pos in positions:
            session.delete(pos)
        session.flush()  # Execute all practice position deletes before deleting lines

    # Delete the lines
    for line in lines:
        session.delete(line)
    session.flush()  # Execute all line deletes before deleting library

    # Delete public signals (stars, comments) for this library
    signals = session.exec(select(PublicSignal).where(PublicSignal.target_id == lib.id)).all()
    for sig in signals:
        session.delete(sig)

    session.flush()

    # Clear forked_from_id references from any libraries that forked from this one
    # This prevents foreign key constraint failures when deleting the library
    forked_libs = session.exec(select(Library).where(Library.forked_from_id == lib.id)).all()
    for forked in forked_libs:
        forked.forked_from_id = None
        session.add(forked)

    session.flush()

    # Delete the library itself
    session.delete(lib)
    session.commit()

    return DeleteOpeningResponse(
        deleted=True,
        message=f"Deleted opening '{lib.name}'."
    )


# ── Logs ──────────────────────────────────────────────────────────────────────


class ActivityLogEntry(BaseModel):
    id: str
    user_id: str | None
    username: str
    action: str
    target: str | None
    detail: str | None
    timestamp: str


@router.get("/logs/activity", response_model=list[ActivityLogEntry])
def get_activity_logs(
    limit: int = Query(default=200, le=1000),
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    from models.activity_log import ActivityLog
    from sqlalchemy import desc
    logs = session.exec(
        select(ActivityLog).order_by(desc(ActivityLog.timestamp)).limit(limit)
    ).all()
    return [
        ActivityLogEntry(
            id=str(log.id),
            user_id=str(log.user_id) if log.user_id else None,
            username=log.username,
            action=log.action,
            target=log.target,
            detail=log.detail,
            timestamp=log.timestamp.isoformat(),
        )
        for log in logs
    ]


def _read_log_tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", errors="replace") as f:
            all_lines = f.readlines()
        return [l.rstrip() for l in all_lines[-lines:]]
    except Exception as e:
        return [f"[error reading log: {e}]"]


@router.get("/logs/backend")
def get_backend_logs(
    lines: int = Query(default=300, le=2000),
    _: User = Depends(require_admin),
):
    from config import settings
    log_path = Path(settings.db_path).parent / "logs" / "backend.log"
    return {"lines": _read_log_tail(log_path, lines)}


@router.get("/logs/frontend")
def get_frontend_logs(
    lines: int = Query(default=300, le=2000),
    _: User = Depends(require_admin),
):
    from config import settings
    log_path = Path(settings.db_path).parent / "logs" / "frontend.log"
    return {"lines": _read_log_tail(log_path, lines)}


@router.post("/openings/delete-all-public", status_code=status.HTTP_200_OK)
def delete_all_public_openings(
    confirm: str = Query(default=""),
    session: Session = Depends(get_session),
):
    """Delete ALL public libraries (for clean reimport). Requires confirm=yes query param."""
    if confirm != "yes":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Must pass confirm=yes to delete all public libraries")
    from models.line import Line
    from models.practice import PracticePosition
    from models.public_signal import PublicSignal

    # Find all public libraries
    libs = session.exec(select(Library).where(Library.is_public == True)).all()  # noqa: E712
    count = len(libs)

    for lib in libs:
        # Delete practice positions
        lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()
        for line in lines:
            positions = session.exec(select(PracticePosition).where(PracticePosition.line_id == line.id)).all()
            for pos in positions:
                session.delete(pos)
            session.delete(line)

        # Delete public signals
        signals = session.exec(select(PublicSignal).where(PublicSignal.target_id == lib.id)).all()
        for sig in signals:
            session.delete(sig)

        # Delete the library
        session.delete(lib)

    session.commit()
    return {"deleted": count, "message": f"Deleted {count} public libraries and all associated data."}


@router.post("/openings/import-lichess-lines", response_model=LichessImportResponse)
def import_lichess_lines(
    body: LichessImportRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Import all opening lines from the Lichess GitHub chess-openings repository
    that match the given library's ECO code. The library must have an eco_code set.
    """
    lib = session.get(Library, body.library_id)
    if not lib:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Library not found")

    if not lib.eco_code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Library must have an eco_code set to import Lichess lines",
        )

    try:
        result = opening_import.import_lichess_lines_into_library(
            body.library_id,
            lib.eco_code,
            session,
        )
        return LichessImportResponse(**result)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to import: {e}")
