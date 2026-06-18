"""End-to-end API smoke test for the My Games feature."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_games_api_test.db"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient


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


def _auth(client):
    client.post("/api/auth/register", json={
        "email": "g@b.com", "username": "gamer", "password": "passw0rd12",
    })
    r = client.post("/api/auth/login", json={"email": "g@b.com", "password": "passw0rd12"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_game_crud_and_notes(client):
    H = _auth(client)

    # Create from a SAN list (frontend parses PGN -> SANs)
    r = client.post("/api/games", headers=H, json={
        "name": "2 May afternoon game",
        "played_date": "2024-05-02",
        "played_color": "black",
        "opponent_level": 1100,
        "result": "win",
        "what_happened": "Strong game.",
        "lesson_learned": "Keep calculating.",
        "repeat_offense": False,
        "moves": ["d4", "d5", "Nc3"],
    })
    assert r.status_code == 201, r.text
    game = r.json()
    assert game["opponent_level"] == 1100
    assert game["result"] == "win"
    assert len(game["moves"]) == 3
    assert game["moves"][0]["uci"] == "d2d4"
    assert "fen_after" in game["moves"][0]

    gid = game["id"]

    # List
    r = client.get("/api/games", headers=H)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Add a move note
    r = client.put(f"/api/games/{gid}/moves/0/note", headers=H, json={"text": "Queen's pawn"})
    assert r.status_code == 200
    assert r.json()["moves"][0]["note"] == "Queen's pawn"

    # Clear the note
    r = client.put(f"/api/games/{gid}/moves/0/note", headers=H, json={"text": ""})
    assert "note" not in r.json()["moves"][0]

    # Update metadata
    r = client.put(f"/api/games/{gid}", headers=H, json={"result": "draw", "repeat_offense": True})
    assert r.status_code == 200
    assert r.json()["result"] == "draw"
    assert r.json()["repeat_offense"] is True

    # Replace moves
    r = client.put(f"/api/games/{gid}/moves", headers=H, json={"moves": ["e4", "c5"]})
    assert r.status_code == 200
    assert [m["san"] for m in r.json()["moves"]] == ["e4", "c5"]

    # Reject an illegal SAN
    r = client.put(f"/api/games/{gid}/moves", headers=H, json={"moves": ["e4", "e9"]})
    assert r.status_code == 422

    # Delete
    r = client.delete(f"/api/games/{gid}", headers=H)
    assert r.status_code == 204
    assert client.get("/api/games", headers=H).json() == []


def test_games_are_owner_scoped(client):
    H1 = _auth(client)
    r = client.post("/api/games", headers=H1, json={
        "name": "mine", "played_color": "white", "result": "win", "moves": ["e4"],
    })
    gid = r.json()["id"]

    # A different user cannot see or fetch it
    client.post("/api/auth/register", json={"email": "h@b.com", "username": "other", "password": "passw0rd12"})
    r = client.post("/api/auth/login", json={"email": "h@b.com", "password": "passw0rd12"})
    H2 = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.get("/api/games", headers=H2).json() == []
    assert client.get(f"/api/games/{gid}", headers=H2).status_code == 403
