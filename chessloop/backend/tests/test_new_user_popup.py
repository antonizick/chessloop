"""New-user announcement popup: per-user flag, admin content CRUD, user-facing read."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_new_user_popup_test.db"
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


def test_new_registration_defaults_popup_flag_true(client):
    H = _register_and_login(client, "new@test.com", "newbie")
    # Announcement doesn't exist/is disabled yet -> null even though the flag is set
    r = client.get("/api/new-user-popup", headers=H)
    assert r.status_code == 200
    assert r.json() is None


def test_admin_can_read_and_update_popup_content(client):
    H_admin = _register_and_login(client, "admin@test.com", "admino", admin=True)

    r = client.get("/api/admin/new-user-popup", headers=H_admin)
    assert r.status_code == 200
    assert r.json() == {"html_content": "", "is_enabled": False}

    r = client.put("/api/admin/new-user-popup", headers=H_admin, json={
        "html_content": "<p>Welcome!</p>", "is_enabled": True,
    })
    assert r.status_code == 200
    assert r.json() == {"html_content": "<p>Welcome!</p>", "is_enabled": True}


def test_non_admin_cannot_access_admin_popup_endpoints(client):
    H = _register_and_login(client, "user@test.com", "regular")
    assert client.get("/api/admin/new-user-popup", headers=H).status_code == 403
    assert client.put("/api/admin/new-user-popup", headers=H, json={
        "html_content": "x", "is_enabled": True,
    }).status_code == 403


def test_user_sees_popup_content_when_enabled_and_flag_set(client):
    H_admin = _register_and_login(client, "admin2@test.com", "admino2", admin=True)
    client.put("/api/admin/new-user-popup", headers=H_admin, json={
        "html_content": "<p>Hi</p>", "is_enabled": True,
    })

    H = _register_and_login(client, "fresh@test.com", "fresh")
    r = client.get("/api/new-user-popup", headers=H)
    assert r.status_code == 200
    assert r.json() == {"html_content": "<p>Hi</p>"}


def test_preferences_can_turn_off_popup(client):
    H_admin = _register_and_login(client, "admin3@test.com", "admino3", admin=True)
    client.put("/api/admin/new-user-popup", headers=H_admin, json={
        "html_content": "<p>Hi</p>", "is_enabled": True,
    })

    H = _register_and_login(client, "toggler@test.com", "toggler")
    assert client.get("/api/new-user-popup", headers=H).json() is not None

    r = client.patch("/api/auth/preferences", headers=H, json={"show_new_user_popup": False})
    assert r.status_code == 200

    r = client.get("/api/new-user-popup", headers=H)
    assert r.status_code == 200
    assert r.json() is None


def test_disabled_announcement_hides_popup_even_with_flag_set(client):
    H = _register_and_login(client, "disabled@test.com", "disabler")
    # Announcement was never enabled by an admin in this test
    r = client.get("/api/new-user-popup", headers=H)
    assert r.status_code == 200
    assert r.json() is None
