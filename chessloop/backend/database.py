from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    # Checkpoint every 100 WAL frames so pooled connections don't miss recent commits
    cursor.execute("PRAGMA wal_autocheckpoint=100;")
    cursor.close()


@event.listens_for(engine, "checkout")
def _wal_checkpoint_on_checkout(dbapi_connection, _connection_record, _connection_proxy):
    # Run a passive checkpoint on each connection checkout so each request
    # sees the latest committed WAL data, not a stale snapshot.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA wal_checkpoint(PASSIVE);")
    cursor.close()


def init_db() -> None:
    import models  # noqa: F401 — ensure models register with SQLModel.metadata
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
