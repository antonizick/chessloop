"""
BackupService — creates, lists, and restores SQLite database backups.

Backups are stored under CHESSLOOP_BACKUP_DIR (default: /data/backups/).
Three types:
  full     — entire DB file copied verbatim (WAL checkpoint first)
  content  — DB containing only Library + Line + MoveNote rows (no users / SRS)
  progress — DB containing only PracticePosition + ReviewLog + PracticeSession rows
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlmodel import Session, select

from config import settings
from models import Backup
from models.user import User


BACKUP_DIR = Path(os.getenv("CHESSLOOP_BACKUP_DIR", "./backups"))
MAX_BACKUPS = 10


def _ensure_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _db_path() -> Path:
    return Path(settings.db_path)


def create_backup(session: Session, name: str, backup_type: str, created_by: UUID) -> Backup:
    _ensure_dir()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{backup_type}_{ts}_{name[:40].replace(' ', '_')}.db"
    dest = BACKUP_DIR / filename

    src = _db_path()
    if not src.exists():
        raise FileNotFoundError(f"Database not found at {src}")

    # Checkpoint WAL before copying to get a consistent snapshot
    conn = sqlite3.connect(str(src))
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        conn.close()

    shutil.copy2(str(src), str(dest))
    size = dest.stat().st_size

    backup = Backup(
        id=uuid4(),
        name=name,
        type=backup_type,
        file_path=str(dest),
        size_bytes=size,
        created_by=created_by,
        created_at=datetime.utcnow(),
    )
    session.add(backup)
    session.commit()
    session.refresh(backup)

    # Prune oldest if over limit
    _prune(session)

    return backup


def _prune(session: Session) -> None:
    backups = session.exec(
        select(Backup).order_by(Backup.created_at.asc())  # type: ignore[arg-type]
    ).all()
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        p = Path(oldest.file_path)
        if p.exists():
            p.unlink()
        session.delete(oldest)
    session.commit()


def get_backup_path(backup: Backup) -> Path:
    return Path(backup.file_path)


def delete_backup(session: Session, backup: Backup) -> None:
    p = Path(backup.file_path)
    if p.exists():
        p.unlink()
    session.delete(backup)
    session.commit()
