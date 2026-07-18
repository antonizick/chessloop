"""Shared pytest fixtures: isolated in-memory SQLite per test."""
import json
import os
from uuid import uuid4

import pytest

# Ensure we use a fresh in-memory DB and don't write WAL files anywhere
os.environ["CHESSLOOP_DB_PATH"] = ":memory:"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"
os.environ["CHESSLOOP_EMAIL_MX_CHECK"] = "false"  # no network access in tests

from sqlmodel import Session, SQLModel, create_engine

import models  # noqa: F401 — register tables
from models import User, Library, Line


@pytest.fixture()
def db():
    """Fresh in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def user(db):
    u = User(
        email="t@t.com",
        username="tester",
        password_hash="x",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def make_library(db, user, *, color="white", name="Italian"):
    lib = Library(name=name, color=color, owner_user_id=user.id)
    db.add(lib)
    db.commit()
    db.refresh(lib)
    return lib


def make_line_with_moves(db, library, moves: list[dict], *, starting_fen=None, name="Main"):
    """moves: list of {san, uci, fen_after}"""
    line = Line(
        library_id=library.id,
        name=name,
        starting_fen=starting_fen or "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        moves=json.dumps(moves),
    )
    db.add(line)
    db.commit()
    db.refresh(line)
    return line
