"""Admin router — backup management + user management + opening import. Requires role='admin'."""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import Backup
from models.user import User
from auth.dependencies import get_current_user
from services import backup_service
from services import opening_import

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


@router.get("/users", response_model=list[UserAdminResponse])
def list_users(
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    users = session.exec(select(User).order_by(User.created_at)).all()  # type: ignore[arg-type]
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


@router.patch("/users/{user_id}", response_model=UserAdminResponse)
def update_user_role(
    user_id: UUID,
    body: PatchUserRoleRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    if body.role not in ("user", "admin"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "role must be 'user' or 'admin'")
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change your own role")
    target.role = body.role
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
    publish: bool = True


class ImportOpeningResponse(BaseModel):
    id: str
    name: str
    status: str  # 'created' | 'exists'


class PullVariationsRequest(BaseModel):
    opening_name: str
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
        )
        for r in results
    ]


@router.post("/openings/seed", response_model=SeedOpeningsResponse)
def seed_openings(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """
    Seed all 16 standard starter opening libraries into the admin's account.
    Already-existing libraries are skipped. New ones are published automatically.
    """
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
            )

            if status_str == "created":
                opening_import.publish_library(lib.id, session)
                seeded += 1
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
    Optionally publishes immediately.
    """
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
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

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

    # Find the library
    lib = session.exec(
        select(LibModel).where(
            LibModel.name == body.opening_name,
            LibModel.owner_user_id == admin.id,
        )
    ).first()

    if not lib:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Opening '{body.opening_name}' not found in your libraries"
        )

    # Find related ECO entries (same base name or ECO prefix)
    base_name = body.opening_name.split(" — ")[0].lower()
    related = [
        e for e in opening_import.ECO_DATABASE
        if (
            base_name in e["name"].lower()
            or (lib.eco_code and e["eco"].startswith(lib.eco_code[0]))
        )
        and e["name"] != body.opening_name  # skip main entry itself
    ][:body.count]

    if not related:
        return PullVariationsResponse(
            opening_name=body.opening_name,
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
        opening_import.publish_library(lib.id, session)

    return PullVariationsResponse(
        opening_name=body.opening_name,
        added=added,
        message=f"Added {added} variation(s) to '{body.opening_name}'." if added
                else "All found variations already exist in this library.",
    )
