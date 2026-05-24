"""End-to-end API smoke test for the practice loop.

Exercises the real FastAPI app via TestClient — register/login, build a library
with a teaching line, start a session, fetch /next, submit /answer (correct AND
wrong), end the session, query due-count.
"""
import os

# Critical: set DB before importing the app
os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_practice_api_test.db"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Fresh client per test. We drop+recreate tables on the shared engine
    because module-level imports hold the engine instance — file-level
    deletion doesn't actually reset state."""
    from sqlmodel import SQLModel
    from database import engine
    import models  # noqa: F401 — ensure all tables are registered

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    from main import app

    with TestClient(app) as c:
        yield c


ITALIAN_OPENING = [
    {"san": "e4",  "uci": "e2e4", "fen_after": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"},
    {"san": "e5",  "uci": "e7e5", "fen_after": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"},
    {"san": "Nf3", "uci": "g1f3", "fen_after": "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"},
    {"san": "Nc6", "uci": "b8c6", "fen_after": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"},
]


def _bootstrap(client):
    """Register, login, create library with one teaching line. Returns (headers, lib, line)."""
    r = client.post("/api/auth/register", json={
        "email": "a@b.com", "username": "alice", "password": "passw0rd12",
    })
    assert r.status_code == 201, r.text

    r = client.post("/api/auth/login", json={"email": "a@b.com", "password": "passw0rd12"})
    assert r.status_code == 200
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post("/api/libraries", headers=H, json={"name": "Italian", "color": "white"})
    assert r.status_code == 201
    lib = r.json()

    r = client.post(f"/api/libraries/{lib['id']}/lines", headers=H, json={"name": "Main"})
    assert r.status_code == 201
    line = r.json()

    for move in ITALIAN_OPENING:
        r = client.post(f"/api/lines/{line['id']}/moves", headers=H, json=move)
        assert r.status_code == 200, r.text

    return H, lib, line


def test_start_session_seeds_positions(client):
    H, lib, _ = _bootstrap(client)
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "weakest"
    # White library, 4 plies → 2 white-to-move positions seeded
    assert data["seeded_positions"] == 2


def test_due_count_after_seeding(client):
    H, _, _ = _bootstrap(client)
    client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    r = client.get("/api/practice/due-count", headers=H)
    assert r.status_code == 200
    data = r.json()
    # 2 white positions, all brand new (repetitions=0, due_at=now), all "new"
    assert data["count"] == 2
    assert data["new"] == 2
    assert data["leeches"] == 0


def test_next_returns_position_then_answer_correct(client):
    H, _, line = _bootstrap(client)
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    sid = r.json()["id"]

    r = client.get(f"/api/practice/session/{sid}/next", headers=H)
    assert r.status_code == 200
    pos = r.json()
    assert pos["done"] is False
    assert pos["turn_color"] == "white"  # white library, only white-to-move positions
    assert pos["is_new"] is True
    assert pos["library_name"] == "Italian"
    assert pos["line_id"] == line["id"]

    # Answer correctly
    expected_uci = ITALIAN_OPENING[pos["move_index"]]["uci"]
    r = client.post(
        f"/api/practice/session/{sid}/answer",
        headers=H,
        json={"practice_position_id": pos["practice_position_id"], "move_uci": expected_uci},
    )
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["correct"] is True
    assert answer["expected_uci"] == expected_uci
    # SRS: first correct → reps=1, interval=1 day
    assert answer["srs"]["repetitions"] == 1
    assert answer["srs"]["interval_days"] == 1.0
    assert answer["srs"]["is_leech"] is False


def test_wrong_answer_increments_leech_count(client):
    H, _, _ = _bootstrap(client)
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    sid = r.json()["id"]

    r = client.get(f"/api/practice/session/{sid}/next", headers=H)
    pos = r.json()

    # Submit a deliberately wrong move
    r = client.post(
        f"/api/practice/session/{sid}/answer",
        headers=H,
        json={"practice_position_id": pos["practice_position_id"], "move_uci": "a2a3"},
    )
    assert r.status_code == 200
    answer = r.json()
    assert answer["correct"] is False
    assert answer["srs"]["leech_count"] == 1
    assert answer["srs"]["is_leech"] is False  # only 1 wrong, threshold is 4
    assert answer["srs"]["repetitions"] == 0


def test_four_wrongs_promote_to_leech(client):
    H, _, _ = _bootstrap(client)
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    sid = r.json()["id"]

    r = client.get(f"/api/practice/session/{sid}/next", headers=H)
    position_id = r.json()["practice_position_id"]

    for i in range(1, 5):
        r = client.post(
            f"/api/practice/session/{sid}/answer",
            headers=H,
            json={"practice_position_id": position_id, "move_uci": "a2a3"},
        )
        assert r.status_code == 200
        leech_count = r.json()["srs"]["leech_count"]
        assert leech_count == i
        if i < 4:
            assert r.json()["srs"]["is_leech"] is False
    # Final state
    assert r.json()["srs"]["is_leech"] is True


def test_leech_drill_mode_returns_leech(client):
    H, _, _ = _bootstrap(client)

    # Make a leech via 4 wrong answers
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    sid = r.json()["id"]
    pos_id = client.get(f"/api/practice/session/{sid}/next", headers=H).json()["practice_position_id"]
    for _ in range(4):
        client.post(
            f"/api/practice/session/{sid}/answer", headers=H,
            json={"practice_position_id": pos_id, "move_uci": "a2a3"},
        )
    client.post(f"/api/practice/session/{sid}/end", headers=H)

    # New leech-drill session
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "leech_drill", "scope": {}})
    sid2 = r.json()["id"]
    r = client.get(f"/api/practice/session/{sid2}/next", headers=H)
    assert r.status_code == 200
    pos = r.json()
    assert pos["done"] is False
    assert pos["is_leech"] is True


def test_session_end_records_stats(client):
    H, _, _ = _bootstrap(client)
    r = client.post("/api/practice/session/start", headers=H, json={"mode": "weakest", "scope": {}})
    sid = r.json()["id"]

    # One correct, one wrong
    pos = client.get(f"/api/practice/session/{sid}/next", headers=H).json()
    expected_uci = ITALIAN_OPENING[pos["move_index"]]["uci"]
    client.post(
        f"/api/practice/session/{sid}/answer", headers=H,
        json={"practice_position_id": pos["practice_position_id"], "move_uci": expected_uci},
    )
    client.post(
        f"/api/practice/session/{sid}/answer", headers=H,
        json={"practice_position_id": pos["practice_position_id"], "move_uci": "a2a3"},
    )

    r = client.post(f"/api/practice/session/{sid}/end", headers=H)
    assert r.status_code == 200
    stats = r.json()["stats"]
    assert stats["correct"] == 1
    assert stats["wrong"] == 1
    assert stats["positions_seen"] == 2


def test_session_must_belong_to_user(client):
    H_a, _, _ = _bootstrap(client)
    sid = client.post("/api/practice/session/start", headers=H_a, json={"mode": "weakest", "scope": {}}).json()["id"]

    # Make a second user, attempt access
    client.post("/api/auth/register", json={"email": "b@b.com", "username": "bob", "password": "passw0rd12"})
    tok = client.post("/api/auth/login", json={"email": "b@b.com", "password": "passw0rd12"}).json()["access_token"]
    H_b = {"Authorization": f"Bearer {tok}"}

    r = client.get(f"/api/practice/session/{sid}/next", headers=H_b)
    assert r.status_code == 403
