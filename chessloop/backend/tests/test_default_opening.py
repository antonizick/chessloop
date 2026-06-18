"""Test that new accounts automatically receive the Ruy López — Closed opening."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_default_opening_test.db"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import User, Library


@pytest.fixture()
def client():
    from sqlmodel import SQLModel
    from database import engine
    import models  # noqa: F401

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    from main import app

    with TestClient(app) as c:
        yield c


def _create_published_ruy_lopez(db_session):
    """Helper to create a published Ruy López — Closed library."""
    from models.published_library import PublishedLibrary, PublishedLine

    # Create an admin user
    admin = User(email="admin@test.com", username="admin", password_hash="x")
    db_session.add(admin)
    db_session.flush()

    # Create the original library
    lib = Library(
        name="Ruy López — Closed",
        color="white",
        eco_code="C84",
        difficulty="intermediate",
        description="3.Bb5 pressures Black's e5 pawn",
        owner_user_id=admin.id,
    )
    db_session.add(lib)
    db_session.flush()

    # Create a published snapshot
    pub_lib = PublishedLibrary(
        original_library_id=lib.id,
        name="Ruy López — Closed",
        color="white",
        eco_code="C84",
        difficulty="intermediate",
        description="3.Bb5 pressures Black's e5 pawn",
        published_by_user_id=admin.id,
    )
    db_session.add(pub_lib)
    db_session.flush()

    # Add a line to the original library
    from models.line import Line
    import json

    line = Line(
        library_id=lib.id,
        name="Main line",
        moves=json.dumps([
            {"san": "e4", "uci": "e2e4"},
            {"san": "e5", "uci": "e7e5"},
        ]),
    )
    db_session.add(line)
    db_session.commit()

    return pub_lib


def test_new_account_receives_default_opening(client):
    """Test that registering a new account automatically clones Ruy López — Closed."""
    # First, create the published library in the database
    from database import engine
    from sqlmodel import Session as SQLSession

    with SQLSession(engine) as db:
        _create_published_ruy_lopez(db)

    # Now register a new user via the API
    r = client.post("/api/auth/register", json={
        "email": "newuser@test.com",
        "username": "newuser",
        "password": "password123",
    })
    assert r.status_code == 201
    new_user_id = r.json()["id"]

    # Get the user's libraries
    r = client.post("/api/auth/login", json={
        "email": "newuser@test.com",
        "password": "password123",
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/libraries", headers=headers)
    assert r.status_code == 200
    libraries = r.json()

    # Should have the Ruy López — Closed library
    assert len(libraries) == 1
    assert libraries[0]["name"] == "Ruy López — Closed"
    assert libraries[0]["color"] == "white"
    assert libraries[0]["eco_code"] == "C84"


def test_registration_succeeds_without_default_opening(client):
    """Test that registration succeeds even if Ruy López library doesn't exist."""
    # Don't create the published library, just register
    r = client.post("/api/auth/register", json={
        "email": "user@test.com",
        "username": "user",
        "password": "password123",
    })
    assert r.status_code == 201
    assert r.json()["username"] == "user"

    # Verify the user can log in
    r = client.post("/api/auth/login", json={
        "email": "user@test.com",
        "password": "password123",
    })
    assert r.status_code == 200
    assert "access_token" in r.json()
