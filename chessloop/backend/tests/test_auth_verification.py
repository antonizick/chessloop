"""End-to-end test for the email-verification loop and the new-account gate on login."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_auth_verification_test.db"
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


def _register(client, email="new@test.com", username="newbie"):
    r = client.post("/api/auth/register", json={
        "email": email, "username": username, "password": "passw0rd12",
    })
    assert r.status_code == 201, r.text
    assert r.json()["email"] == email
    return r


def _token_for(email):
    from database import engine
    from sqlmodel import Session, select
    from models import User
    from auth import jwt as jwt_utils

    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        return jwt_utils.create_email_verification_token(u.id)


def test_login_blocked_until_verified(client):
    _register(client)
    r = client.post("/api/auth/login", json={"email": "new@test.com", "password": "passw0rd12"})
    assert r.status_code == 403


def test_verify_email_then_login_succeeds(client):
    _register(client)
    token = _token_for("new@test.com")

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    assert "access_token" in r.json()

    r = client.post("/api/auth/login", json={"email": "new@test.com", "password": "passw0rd12"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_verify_email_rejects_bad_token(client):
    _register(client)
    r = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 401


def test_verify_email_rejects_wrong_token_type(client):
    """A refresh token must not double as a verification token."""
    from database import engine
    from sqlmodel import Session, select
    from models import User
    from auth import jwt as jwt_utils

    _register(client)
    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == "new@test.com")).first()
        refresh_token = jwt_utils.create_refresh_token(u.id)

    r = client.post("/api/auth/verify-email", json={"token": refresh_token})
    assert r.status_code == 401


def test_resend_verification_does_not_leak_account_existence(client):
    _register(client)
    r = client.post("/api/auth/resend-verification", json={"email": "new@test.com"})
    assert r.status_code == 204

    r = client.post("/api/auth/resend-verification", json={"email": "nobody@test.com"})
    assert r.status_code == 204
