"""Phase 12 security review fixes: no special username (F-050), the
unauthenticated client-log endpoint, the MFA code limit and upload names."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_first_run_access_test.db"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"
os.environ["CHESSLOOP_EMAIL_MX_CHECK"] = "false"

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

PW = "Kn1ght-to-f3!"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    from sqlmodel import SQLModel
    from database import engine
    from config import settings
    import models  # noqa: F401
    import main

    monkeypatch.setattr(settings, "email_verification", "off")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(main, "_FRONTEND_LOG_PATH", tmp_path / "logs" / "frontend.log")
    monkeypatch.setattr(main, "_frontend_log", None)
    import logging
    logging.getLogger("chessloop.frontend").handlers.clear()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    from routers.auth import CHANGE_PASSWORD_LIMIT, MFA_CODE_LIMIT

    CHANGE_PASSWORD_LIMIT.reset()
    MFA_CODE_LIMIT.reset()
    main.CLIENT_LOG_RATE.reset()
    with TestClient(main.app) as c:
        yield c
    logging.getLogger("chessloop.frontend").handlers.clear()


def _session():
    from database import engine
    return Session(engine)


def _signup(client, email, username, role="user"):
    r = client.post("/api/auth/register", json={"email": email, "username": username, "password": PW})
    assert r.status_code == 201, r.text
    if role != "user":
        from models import User
        with _session() as s:
            u = s.exec(select(User).where(User.email == email)).first()
            u.role = role
            s.add(u)
            s.commit()
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _library(client, headers, name="Mine"):
    r = client.post("/api/libraries", json={"name": name, "color": "white"}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ── F-050: the username "nick" is not special ────────────────────────────
def test_user_named_nick_cannot_touch_other_libraries(client):
    owner = _signup(client, "owner@test.com", "owner")
    lib = _library(client, owner)
    nick = _signup(client, "nick@test.com", "nick")
    assert client.post(f"/api/libraries/{lib}/publish", headers=nick).status_code == 403
    assert client.get(f"/api/libraries/{lib}/lines", headers=nick).status_code == 403


def test_owner_and_admin_still_can(client):
    owner = _signup(client, "owner@test.com", "owner")
    lib = _library(client, owner)
    admin = _signup(client, "boss@test.com", "boss", role="admin")
    assert client.get(f"/api/libraries/{lib}/lines", headers=owner).status_code == 200
    assert client.get(f"/api/libraries/{lib}/lines", headers=admin).status_code == 200
    assert client.post(f"/api/libraries/{lib}/publish", headers=admin).status_code == 200


# ── POST /api/logs/client: no sign-in, so everything is capped ───────────
def _frontend_lines():
    import main
    return main._FRONTEND_LOG_PATH.read_text().splitlines()


def test_client_log_cannot_forge_lines(client):
    msg = "boom\n2026-01-01T00:00:00 [INFO] admin logged in"
    assert client.post("/api/logs/client", json={"message": msg, "level": "error\nx"}).status_code == 204
    lines = _frontend_lines()
    assert len(lines) == 1
    assert "[ERROR X] boom 2026-01-01" in lines[0]


def test_client_log_fields_are_capped(client):
    big = "A" * 50_000
    client.post("/api/logs/client", json={"message": big, "url": big, "stack": big})
    text = "\n".join(_frontend_lines())
    assert len(text) < 11_000


def test_client_log_stack_stays_indented(client):
    client.post("/api/logs/client", json={"message": "x", "stack": "Error: x\n  at a.js:1\n  at b.js:2"})
    lines = _frontend_lines()
    assert len(lines) == 4
    assert all(line.startswith("  ") for line in lines[1:])


def test_client_log_rate_limited_per_address(client):
    for i in range(40):
        client.post("/api/logs/client", json={"message": f"m{i}"}, headers={"X-Real-IP": "10.0.0.9"})
    assert len(_frontend_lines()) == 30
    client.post("/api/logs/client", json={"message": "other"}, headers={"X-Real-IP": "10.0.0.10"})
    assert len(_frontend_lines()) == 31


def test_client_log_file_rotates(client):
    import main
    from logging.handlers import RotatingFileHandler
    rotating = [h for h in main._frontend_logger().handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) == 1
    handler = rotating[0]
    assert handler.maxBytes == 1024 * 1024 and handler.backupCount == 2


# ── MFA codes: 5 wrong ones, then a pause ────────────────────────────────
def _enable_mfa(client, headers):
    secret = client.post("/api/auth/mfa/setup", headers=headers).json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert client.post("/api/auth/mfa/confirm", json={"totp_code": code}, headers=headers).status_code == 204
    return secret


def test_mfa_code_guessing_is_limited(client):
    headers = _signup(client, "sam@test.com", "sam")
    secret = _enable_mfa(client, headers)
    challenge = client.post("/api/auth/login", json={"email": "sam@test.com", "password": PW}).json()
    token = challenge["challenge_token"]
    good = pyotp.TOTP(secret).now()
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        r = client.post("/api/auth/login/mfa", json={"challenge_token": token, "totp_code": bad})
        assert r.status_code == 401
    r = client.post("/api/auth/login/mfa", json={"challenge_token": token, "totp_code": good})
    assert r.status_code == 429
    assert "15 minutes" in r.json()["detail"]


def test_mfa_right_code_works_after_a_few_wrong(client):
    headers = _signup(client, "sam@test.com", "sam")
    secret = _enable_mfa(client, headers)
    token = client.post("/api/auth/login", json={"email": "sam@test.com", "password": PW}).json()["challenge_token"]
    good = pyotp.TOTP(secret).now()
    bad = "000000" if good != "000000" else "111111"
    for _ in range(3):
        client.post("/api/auth/login/mfa", json={"challenge_token": token, "totp_code": bad})
    r = client.post("/api/auth/login/mfa", json={"challenge_token": token, "totp_code": good})
    assert r.status_code == 200 and "access_token" in r.json()


# ── Admin backup upload: the browser's name never becomes a path ─────────
def test_upload_name_is_made_safe(client, tmp_path, monkeypatch):
    from services import backup_service
    monkeypatch.setattr(backup_service, "_ensure_dir", lambda: tmp_path)
    admin = _signup(client, "boss@test.com", "boss", role="admin")
    data = b"SQLite format 3\x00" + b"\x00" * 100
    r = client.post(
        "/api/admin/backups/upload",
        files={"file": ("x.db", data, "application/octet-stream")},
        data={"name": "../../etc/evil name"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    files = [p.name for p in tmp_path.iterdir()]
    assert len(files) == 1
    assert "/" not in files[0] and ".." not in files[0]
    assert files[0].endswith("_etc_evil_name.db")
