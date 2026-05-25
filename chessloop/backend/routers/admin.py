"""Admin router — backup management + user management. Requires role='admin'."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import Backup
from models.user import User
from auth.dependencies import get_current_user
from services import backup_service

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
