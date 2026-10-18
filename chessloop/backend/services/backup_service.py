"""
BackupService — creates, lists, and restores SQLite database backups.

Backups are stored under CHESSLOOP_BACKUP_DIR (default: /data/backups/).
They hold password hashes and TOTP secrets, so the folder is mode 700 and
every file mode 600 (spec S5).
Three types:
  full     — entire DB file copied verbatim (WAL checkpoint first)
  content  — DB containing only Library + Line + MoveNote rows (no users / SRS)
  progress — DB containing only PracticePosition + ReviewLog + PracticeSession rows
"""

import os
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
    _chmod(BACKUP_DIR, 0o700)
    return BACKUP_DIR


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass  # e.g. a mounted folder that doesn't support modes; the backup itself still works


def secure_file(path: Path) -> None:
    """Make a backup file readable by its owner only."""
    _chmod(path, 0o600)


def secure_backup_dir() -> None:
    """Tighten backups written before this rule existed (called at startup)."""
    if not BACKUP_DIR.is_dir():
        return
    _chmod(BACKUP_DIR, 0o700)
    for p in BACKUP_DIR.iterdir():
        if p.is_file():
            secure_file(p)


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

    # SQLite's online backup API gives a consistent copy even while the app
    # writes (a file copy after a checkpoint could catch a write half-way).
    src_conn = sqlite3.connect(str(src))
    dest_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dest_conn)
    finally:
        src_conn.close()
        dest_conn.close()
    secure_file(dest)
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


def restore_backup(backup: Backup) -> None:
    src = Path(backup.file_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup file missing: {src}")

    dst = _db_path()
    known_backups = _backup_rows(dst)

    # WAL checkpoint the backup source first to ensure consistent snapshot
    src_conn = sqlite3.connect(str(src))
    try:
        src_conn.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        src_conn.close()

    # Use SQLite's online backup API to safely overwrite live DB
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()

    carry_over_backup_rows(dst, known_backups)


def _backup_rows(db: Path) -> list[dict]:
    """The rows of the backup table, as plain dicts (empty if there is none)."""
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute('SELECT * FROM "backup"')]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def carry_over_backup_rows(db: Path, rows: list[dict]) -> int:
    """Put back the backup-list entries that a restore would lose (F-033).

    The restored copy is older than the backups made after it, usually even
    older than its own entry, so those rows disappear from Admin → Backups
    although the files are still in the backup folder. Re-add each row whose
    file still exists. A row whose creator isn't in the restored database is
    credited to its first admin (the column is a foreign key).
    Returns the number of rows added.
    """
    if not rows:
        return 0
    conn = sqlite3.connect(str(db))
    try:
        cols = [r[1] for r in conn.execute('PRAGMA table_info("backup")')]
        if not cols:
            return 0
        present = {r[0] for r in conn.execute('SELECT id FROM "backup"')}
        users = {r[0] for r in conn.execute('SELECT id FROM "user"')}
        first_admin = conn.execute(
            'SELECT id FROM "user" WHERE role = \'admin\' ORDER BY rowid LIMIT 1'
        ).fetchone()
        added = 0
        for row in rows:
            if row.get("id") in present or not Path(str(row.get("file_path", ""))).exists():
                continue
            if row.get("created_by") not in users:
                if first_admin is None:
                    continue
                row = {**row, "created_by": first_admin[0]}
            use = [c for c in cols if c in row]
            names = ", ".join(f'"{c}"' for c in use)
            marks = ", ".join("?" for _ in use)
            conn.execute(f'INSERT INTO "backup" ({names}) VALUES ({marks})', [row[c] for c in use])
            added += 1
        conn.commit()
        return added
    finally:
        conn.close()
