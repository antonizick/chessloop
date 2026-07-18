"""Site-wide banner: admin content CRUD, per-user dismiss, version-based reset on content change."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_banner_test.db"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"
os.environ["CHESSLOOP_EMAIL_MX_CHECK"] = "false"

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


def _verify(email):
    from database import engine
    from sqlmodel import Session, select
    from models import User

    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        u.is_verified = True
        s.add(u)
        s.commit()


def _make_admin(email):
    from database import engine
    from sqlmodel import Session, select
    from models import User

    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        u.role = "admin"
        s.add(u)
        s.commit()


def _register_and_login(client, email, username, admin=False):
    client.post("/api/auth/register", json={
        "email": email, "username": username, "password": "passw0rd12",
    })
    _verify(email)
    if admin:
        _make_admin(email)
    r = client.post("/api/auth/login", json={"email": email, "password": "passw0rd12"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_banner_hidden_when_disabled(client):
    H = _register_and_login(client, "u1@test.com", "user1")
    r = client.get("/api/banner", headers=H)
    assert r.status_code == 200
    assert r.json() is None


def test_non_admin_cannot_access_admin_banner_endpoints(client):
    H = _register_and_login(client, "u2@test.com", "user2")
    assert client.get("/api/admin/banner", headers=H).status_code == 403
    assert client.put("/api/admin/banner", headers=H, json={
        "html_content": "x", "is_enabled": True,
    }).status_code == 403


def test_user_sees_banner_when_enabled(client):
    H_admin = _register_and_login(client, "admin1@test.com", "admin1", admin=True)
    client.put("/api/admin/banner", headers=H_admin, json={
        "html_content": "<p>Scheduled maintenance</p>", "is_enabled": True,
    })

    H = _register_and_login(client, "u3@test.com", "user3")
    r = client.get("/api/banner", headers=H)
    assert r.status_code == 200
    assert r.json() == {"html_content": "<p>Scheduled maintenance</p>", "version": 2}


def test_dismiss_permanently_hides_banner_until_content_changes(client):
    H_admin = _register_and_login(client, "admin2@test.com", "admin2", admin=True)
    client.put("/api/admin/banner", headers=H_admin, json={
        "html_content": "<p>Hi</p>", "is_enabled": True,
    })

    H = _register_and_login(client, "u4@test.com", "user4")
    assert client.get("/api/banner", headers=H).json() is not None

    r = client.post("/api/banner/dismiss", headers=H)
    assert r.status_code == 204
    assert client.get("/api/banner", headers=H).json() is None

    # Admin changes content -> banner reappears for the same user without any per-user reset
    client.put("/api/admin/banner", headers=H_admin, json={
        "html_content": "<p>New content</p>", "is_enabled": True,
    })
    r = client.get("/api/banner", headers=H)
    assert r.status_code == 200
    assert r.json()["html_content"] == "<p>New content</p>"


def test_updating_banner_without_content_change_does_not_reset_dismissals(client):
    H_admin = _register_and_login(client, "admin3@test.com", "admin3", admin=True)
    client.put("/api/admin/banner", headers=H_admin, json={
        "html_content": "<p>Hi</p>", "is_enabled": True,
    })

    H = _register_and_login(client, "u5@test.com", "user5")
    client.post("/api/banner/dismiss", headers=H)
    assert client.get("/api/banner", headers=H).json() is None

    # Same content, re-saved (e.g. just re-toggling enabled) -> stays dismissed
    client.put("/api/admin/banner", headers=H_admin, json={
        "html_content": "<p>Hi</p>", "is_enabled": True,
    })
    assert client.get("/api/banner", headers=H).json() is None


def test_system_settings_toggle_controls_new_registration_verification(client):
    H_admin = _register_and_login(client, "admin4@test.com", "admin4", admin=True)

    r = client.get("/api/admin/system-settings", headers=H_admin)
    assert r.status_code == 200
    assert r.json() == {"enforce_email_verification": True}

    r = client.put("/api/admin/system-settings", headers=H_admin, json={
        "enforce_email_verification": False,
    })
    assert r.status_code == 200
    assert r.json() == {"enforce_email_verification": False}

    # New account registers while enforcement is off -> can log in without verifying
    client.post("/api/auth/register", json={
        "email": "skipverify@test.com", "username": "skipverify", "password": "passw0rd12",
    })
    r = client.post("/api/auth/login", json={"email": "skipverify@test.com", "password": "passw0rd12"})
    assert r.status_code == 200, r.text


def test_non_admin_cannot_access_system_settings(client):
    H = _register_and_login(client, "u6@test.com", "user6")
    assert client.get("/api/admin/system-settings", headers=H).status_code == 403
    assert client.put("/api/admin/system-settings", headers=H, json={
        "enforce_email_verification": False,
    }).status_code == 403
