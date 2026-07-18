"""End-to-end tests for the forgot-password / reset-password flow."""
import os

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_password_reset_test.db"
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


def _register_and_verify(client, email="reset@test.com", username="resetter", password="passw0rd12"):
    r = client.post("/api/auth/register", json={"email": email, "username": username, "password": password})
    assert r.status_code == 201, r.text

    from database import engine
    from sqlmodel import Session, select
    from models import User
    from auth import jwt as jwt_utils

    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        verify_token = jwt_utils.create_email_verification_token(u.id)
    client.post("/api/auth/verify-email", json={"token": verify_token})


def _reset_token_for(email):
    from database import engine
    from sqlmodel import Session, select
    from models import User
    from auth import jwt as jwt_utils

    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).first()
        return jwt_utils.create_password_reset_token(u.id, u.password_hash)


def test_reset_password_then_login_with_new_password(client):
    _register_and_verify(client)
    token = _reset_token_for("reset@test.com")

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpassw0rd"})
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()

    r = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "newpassw0rd"})
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "passw0rd12"})
    assert r.status_code == 401


def test_reset_password_allows_same_password(client):
    _register_and_verify(client)
    token = _reset_token_for("reset@test.com")

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "passw0rd12"})
    assert r.status_code == 200, r.text

    r = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "passw0rd12"})
    assert r.status_code == 200


def test_reset_password_token_is_single_use(client):
    _register_and_verify(client)
    token = _reset_token_for("reset@test.com")

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpassw0rd"})
    assert r.status_code == 200

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "anotherpassw0rd"})
    assert r.status_code == 401


def test_validate_reset_token_reflects_single_use(client):
    """The read-only validate check must agree with reset-password: valid before use, dead after."""
    _register_and_verify(client)
    token = _reset_token_for("reset@test.com")

    r = client.get("/api/auth/reset-password/validate", params={"token": token})
    assert r.status_code == 204

    client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpassw0rd"})

    r = client.get("/api/auth/reset-password/validate", params={"token": token})
    assert r.status_code == 401


def test_validate_reset_token_does_not_consume_it(client):
    """Merely checking a link (e.g. an email client prefetching it) must not burn it."""
    _register_and_verify(client)
    token = _reset_token_for("reset@test.com")

    for _ in range(3):
        r = client.get("/api/auth/reset-password/validate", params={"token": token})
        assert r.status_code == 204

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpassw0rd"})
    assert r.status_code == 200, r.text


def test_reset_password_rejects_bad_token(client):
    _register_and_verify(client)
    r = client.post("/api/auth/reset-password", json={"token": "not-a-real-token", "new_password": "newpassw0rd"})
    assert r.status_code == 401


def test_reset_password_rejects_wrong_token_type(client):
    """A verification token must not double as a reset token."""
    from database import engine
    from sqlmodel import Session, select
    from models import User
    from auth import jwt as jwt_utils

    _register_and_verify(client)
    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == "reset@test.com")).first()
        verify_token = jwt_utils.create_email_verification_token(u.id)

    r = client.post("/api/auth/reset-password", json={"token": verify_token, "new_password": "newpassw0rd"})
    assert r.status_code == 401


def test_reset_password_can_disable_existing_mfa(client):
    _register_and_verify(client)

    login = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "passw0rd12"})
    access = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    setup = client.post("/api/auth/mfa/setup", headers=headers)
    secret = setup.json()["secret"]

    import pyotp
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/auth/mfa/confirm", json={"totp_code": code}, headers=headers)
    assert r.status_code == 204

    token = _reset_token_for("reset@test.com")
    r = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "newpassw0rd", "disable_mfa": True},
    )
    assert r.status_code == 200, r.text

    r = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "newpassw0rd"})
    assert r.status_code == 200
    assert "mfa_required" not in r.json()


def test_reset_password_without_disable_mfa_keeps_existing_mfa(client):
    _register_and_verify(client)

    login = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "passw0rd12"})
    access = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    setup = client.post("/api/auth/mfa/setup", headers=headers)
    secret = setup.json()["secret"]

    import pyotp
    code = pyotp.TOTP(secret).now()
    client.post("/api/auth/mfa/confirm", json={"totp_code": code}, headers=headers)

    token = _reset_token_for("reset@test.com")
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpassw0rd"})
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"email": "reset@test.com", "password": "newpassw0rd"})
    assert r.status_code == 200
    assert r.json().get("mfa_required") is True


def test_forgot_password_does_not_leak_account_existence(client):
    _register_and_verify(client)
    r = client.post("/api/auth/forgot-password", json={"email": "reset@test.com"})
    assert r.status_code == 204

    r = client.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
    assert r.status_code == 204
