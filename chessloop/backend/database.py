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


def _sql_literal(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


# Backfill value for existing rows, when it must differ from the model's default
# for newly-inserted rows. e.g. is_verified defaults False for new signups, but
# accounts that predate the verification feature must be grandfathered in as
# already-verified rather than locked out of login on upgrade.
_BACKFILL_OVERRIDES: dict[tuple[str, str], object] = {
    ("user", "is_verified"): True,
}


def _ensure_columns() -> None:
    """Add any model columns missing from existing SQLite tables.

    SQLModel.metadata.create_all() only creates missing tables — it never alters
    existing ones. There's no migration tool in this project, so new columns added
    to a model (e.g. a new bool flag on User) would 500 on every existing install
    without this. Only handles columns with a plain scalar default (or an explicit
    override above); a callable default (e.g. default_factory) is skipped.
    """
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {
                row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")').fetchall()
            }
            if not existing:
                continue  # table itself is new — create_all() already built it in full
            for column in table.columns:
                if column.name in existing:
                    continue
                override_key = (table.name, column.name)
                if override_key in _BACKFILL_OVERRIDES:
                    backfill_value = _BACKFILL_OVERRIDES[override_key]
                elif column.default is not None and not column.default.is_callable:
                    backfill_value = column.default.arg
                else:
                    continue  # lucent: scalar defaults only — add an override above if this needs backfill
                col_type = column.type.compile(dialect=conn.dialect)
                default_clause = f" DEFAULT {_sql_literal(backfill_value)}"
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_clause}'
                )


def init_db() -> None:
    import models  # noqa: F401 — ensure models register with SQLModel.metadata
    SQLModel.metadata.create_all(engine)
    _ensure_columns()


def get_session():
    with Session(engine) as session:
        yield session
