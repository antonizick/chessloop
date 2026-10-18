"""Admin-panel backups: private file modes (S5) and the backup list surviving a
restore (F-033). Uses a real SQLite file, because backups copy files."""
import stat

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

# Imported inside the fixture: importing config at collection time would fix
# the database path of test modules that set it themselves.
backup_service = Backup = Library = None


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """A file database plus a backup folder, wired into backup_service."""
    global backup_service, Backup, Library
    import models  # noqa: F401 — register tables
    from models import Backup, Library, User
    from services import backup_service
    db_file = tmp_path / "chessloop.db"
    engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(backup_service, "_db_path", lambda: db_file)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path / "backups")
    with Session(engine) as s:
        admin = User(email="boss@test.com", username="boss", password_hash="x", role="admin", is_verified=True)
        s.add(admin)
        s.commit()
        s.refresh(admin)
        yield engine, admin.id
    engine.dispose()


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_backup_files_are_private(live, tmp_path):
    engine, admin_id = live
    with Session(engine) as s:
        path = backup_service.get_backup_path(backup_service.create_backup(s, "first", "full", admin_id))
    assert _mode(tmp_path / "backups") == 0o700
    assert _mode(path) == 0o600


def test_secure_backup_dir_tightens_old_files(live, tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir(mode=0o755)
    old = folder / "full_20260101_000000_old.db"
    old.write_bytes(b"SQLite format 3\x00")
    old.chmod(0o644)
    backup_service.secure_backup_dir()
    assert _mode(folder) == 0o700
    assert _mode(old) == 0o600


def test_backup_is_a_consistent_copy(live, tmp_path):
    engine, admin_id = live
    with Session(engine) as s:
        s.add(Library(name="Italian", color="white", owner_user_id=admin_id))
        s.commit()
        path = backup_service.get_backup_path(backup_service.create_backup(s, "with library", "full", admin_id))
    copy = create_engine(f"sqlite:///{path}")
    with Session(copy) as s:
        assert [lib.name for lib in s.exec(select(Library)).all()] == ["Italian"]
    copy.dispose()


def test_restore_keeps_the_backup_list(live):
    """F-033: the restored database predates its own backup row."""
    engine, admin_id = live
    with Session(engine) as s:
        first = backup_service.create_backup(s, "before library", "full", admin_id)
        s.add(Library(name="Italian", color="white", owner_user_id=admin_id))
        s.commit()
        second = backup_service.create_backup(s, "after library", "full", admin_id)
        first_id, second_id = first.id, second.id
        backup_service.restore_backup(first)

    with Session(engine) as s:
        assert s.exec(select(Library)).all() == []  # the data really is the old copy
        names = sorted(b.name for b in s.exec(select(Backup)).all())
        assert names == ["after library", "before library"]
        assert {first_id, second_id} == {b.id for b in s.exec(select(Backup)).all()}


def test_restore_skips_rows_whose_file_is_gone(live):
    engine, admin_id = live
    with Session(engine) as s:
        first = backup_service.create_backup(s, "kept", "full", admin_id)
        gone = backup_service.create_backup(s, "deleted on disk", "full", admin_id)
        backup_service.get_backup_path(gone).unlink()
        backup_service.restore_backup(first)
    with Session(engine) as s:
        assert [b.name for b in s.exec(select(Backup)).all()] == ["kept"]


def test_carry_over_credits_unknown_creator_to_an_admin(live, tmp_path):
    engine, admin_id = live
    f = tmp_path / "orphan.db"
    f.write_bytes(b"x")
    rows = [{"id": "0" * 32, "name": "from elsewhere", "type": "full", "file_path": str(f),
             "size_bytes": 1, "created_by": "f" * 32, "created_at": "2026-10-17 10:00:00"}]
    assert backup_service.carry_over_backup_rows(backup_service._db_path(), rows) == 1
    with Session(engine) as s:
        (row,) = s.exec(select(Backup)).all()
        assert row.created_by == admin_id
