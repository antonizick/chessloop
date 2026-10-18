"""First-run access: verification policy, /auth/config, change-password and
token revocation, admin user management, create_admin.py and direct seeding."""
import importlib.util
import io
import os
from pathlib import Path

os.environ["CHESSLOOP_DB_PATH"] = "/tmp/chessloop_first_run_access_test.db"
os.environ["CHESSLOOP_JWT_SECRET"] = "test-secret"
os.environ["CHESSLOOP_EMAIL_MX_CHECK"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

PW = "Kn1ght-to-f3!"
NEW_PW = "Bish0p-to-c4!"


@pytest.fixture()
def client(monkeypatch):
    from sqlmodel import SQLModel
    from database import engine
    from config import settings
    import models  # noqa: F401

    monkeypatch.setattr(settings, "email_verification", "auto")
    monkeypatch.setattr(settings, "smtp_host", "")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    from main import app
    from routers.auth import CHANGE_PASSWORD_LIMIT

    CHANGE_PASSWORD_LIMIT.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sent(monkeypatch):
    """Capture verification emails instead of sending them."""
    outbox: list[str] = []
    monkeypatch.setattr("routers.auth.send_verification_email", lambda to, token: outbox.append(to))
    return outbox


def _session():
    from database import engine
    return Session(engine)


def _user(email):
    from models import User
    with _session() as s:
        return s.exec(select(User).where(User.email == email)).first()


def _register(client, email="sam@test.com", username="sam", password=PW):
    return client.post("/api/auth/register", json={"email": email, "username": username, "password": password})


def _login(client, email="sam@test.com", password=PW):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _make_admin(email):
    from models import User
    with _session() as s:
        u = s.exec(select(User).where(User.email == email)).first()
        u.role = "admin"
        u.is_verified = True
        s.add(u)
        s.commit()


def _admin_headers(client, email="boss@test.com", username="boss"):
    _register(client, email, username)
    _make_admin(email)
    tok = _login(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _set_admin_row(value: bool):
    from models.system_settings import SystemSettings
    with _session() as s:
        s.add(SystemSettings(enforce_email_verification=value))
        s.commit()


# ── Verification policy matrix ───────────────────────────────────────────────


def test_auto_without_smtp_lets_new_users_log_in(client, sent):
    r = _register(client)
    assert r.status_code == 201
    assert "log in now" in r.json()["message"] and r.json()["next_step"] == "login"
    assert _login(client).status_code == 200
    assert sent == []


def test_auto_with_smtp_requires_verification(client, sent, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "smtp_host", "mail.test")
    r = _register(client)
    assert r.status_code == 201
    assert "Check your email" in r.json()["message"] and r.json()["next_step"] == "check_email"
    assert sent == ["sam@test.com"]
    assert _login(client).status_code == 403


def test_mode_on_requires_verification_even_without_smtp(client, sent, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "email_verification", "on")
    r = _register(client)
    assert "ask your ChessLoop admin" in r.json()["message"] and r.json()["next_step"] == "ask_admin"
    assert sent == []  # nothing can be sent, so nothing is attempted
    assert _login(client).status_code == 403


def test_mode_off_skips_verification_even_with_smtp(client, sent, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "smtp_host", "mail.test")
    monkeypatch.setattr(settings, "email_verification", "off")
    _register(client)
    assert _login(client).status_code == 200
    assert sent == []


@pytest.mark.parametrize("row_value, expect_login", [(True, 403), (False, 200)])
def test_existing_admin_row_overrides_config(client, sent, monkeypatch, row_value, expect_login):
    from config import settings
    # Config says the opposite of the admin's stored choice
    monkeypatch.setattr(settings, "email_verification", "off" if row_value else "on")
    _set_admin_row(row_value)
    _register(client)
    assert _login(client).status_code == expect_login


def test_mode_is_case_insensitive():
    from config import Settings
    assert Settings(email_verification=" ON ").email_verification == "on"
    assert Settings(email_verification="").email_verification == "auto"


# ── /auth/config ─────────────────────────────────────────────────────────────


def test_auth_config_without_smtp(client):
    r = client.get("/api/auth/config")
    assert r.status_code == 200
    assert r.json() == {
        "registration_open": True,
        "email_verification": False,
        "smtp_configured": False,
        "password_min_length": 12,
    }


def test_auth_config_with_smtp_reveals_no_secrets(client, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "smtp_host", "mail.secret-host.test")
    monkeypatch.setattr(settings, "smtp_password", "hunter2-hunter2")
    body = client.get("/api/auth/config").text
    assert '"smtp_configured":true' in body and '"email_verification":true' in body
    assert "secret-host" not in body and "hunter2" not in body


# ── Admin system settings ────────────────────────────────────────────────────


def test_get_system_settings_does_not_freeze_the_default(client):
    from models.system_settings import SystemSettings
    H = _admin_headers(client)
    r = client.get("/api/admin/system-settings", headers=H)
    assert r.json() == {
        "enforce_email_verification": False, "source": "config",
        "config_mode": "auto", "smtp_configured": False,
    }
    with _session() as s:
        assert s.exec(select(SystemSettings)).first() is None


def test_turning_verification_on_without_smtp_is_refused(client):
    H = _admin_headers(client)
    r = client.put("/api/admin/system-settings", headers=H, json={"enforce_email_verification": True})
    assert r.status_code == 409
    assert "SMTP" in r.json()["detail"]


def test_turning_verification_on_with_smtp_and_clearing_it(client, monkeypatch):
    from config import settings
    H = _admin_headers(client)
    monkeypatch.setattr(settings, "smtp_host", "mail.test")
    monkeypatch.setattr(settings, "email_verification", "off")
    r = client.put("/api/admin/system-settings", headers=H, json={"enforce_email_verification": True})
    assert r.status_code == 200
    assert r.json()["enforce_email_verification"] is True and r.json()["source"] == "admin"

    r = client.put("/api/admin/system-settings", headers=H, json={"enforce_email_verification": None})
    assert r.status_code == 200
    assert r.json()["source"] == "config" and r.json()["enforce_email_verification"] is False


# ── Password rule ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("weak", ["short1!", "passw0rd1234", "Chessloop2026!", "123456789012", "aaaaaaaaaaaa"])
def test_register_rejects_weak_passwords(client, weak):
    r = _register(client, password=weak)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)  # a sentence the UI can show


# ── Change password ──────────────────────────────────────────────────────────


def _signed_in(client):
    _register(client)
    tokens = _login(client).json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


def test_change_password_success_revokes_old_tokens(client):
    old, H = _signed_in(client)
    r = client.post("/api/auth/change-password", headers=H,
                    json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    new = r.json()

    # Old refresh and access tokens are dead; the new ones work
    assert client.post("/api/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    assert client.get("/api/auth/me", headers=H).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"}).status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 200

    assert _login(client, password=PW).status_code == 401
    assert _login(client, password=NEW_PW).status_code == 200


def test_change_password_wrong_current(client):
    _, H = _signed_in(client)
    r = client.post("/api/auth/change-password", headers=H,
                    json={"current_password": "not-my-password", "new_password": NEW_PW})
    assert r.status_code == 400
    assert _login(client, password=PW).status_code == 200


def test_change_password_weak_or_same(client):
    _, H = _signed_in(client)
    weak = client.post("/api/auth/change-password", headers=H,
                       json={"current_password": PW, "new_password": "password2026"})
    same = client.post("/api/auth/change-password", headers=H,
                       json={"current_password": PW, "new_password": PW})
    assert weak.status_code == 422 and same.status_code == 422


def test_change_password_requires_login(client):
    r = client.post("/api/auth/change-password", json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 401


def test_change_password_rate_limited(client):
    _, H = _signed_in(client)
    for _ in range(5):
        r = client.post("/api/auth/change-password", headers=H,
                        json={"current_password": "wrong-wrong-wrong", "new_password": NEW_PW})
        assert r.status_code == 400
    r = client.post("/api/auth/change-password", headers=H,
                    json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 429


def test_reset_password_also_revokes_old_tokens(client):
    from auth import jwt as jwt_utils
    old, _ = _signed_in(client)
    u = _user("sam@test.com")
    token = jwt_utils.create_password_reset_token(u.id, u.password_hash)
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": NEW_PW}).status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401


def test_tokens_from_before_the_upgrade_still_work(client):
    """Tokens issued before the "tv" claim existed must not log everyone out."""
    from auth.jwt import _encode
    from datetime import timedelta
    _register(client)
    u = _user("sam@test.com")
    legacy = _encode(str(u.id), timedelta(minutes=5), "access")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200


# ── Admin user management ────────────────────────────────────────────────────


def test_admin_created_user_is_verified_and_can_log_in(client, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "email_verification", "on")
    H = _admin_headers(client)
    r = client.post("/api/admin/users", headers=H,
                    json={"email": "kid@test.com", "username": "kid", "password": PW})
    assert r.status_code == 201 and r.json()["is_verified"] is True
    assert _login(client, "kid@test.com").status_code == 200


def test_admin_can_verify_a_user(client, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "email_verification", "on")
    H = _admin_headers(client)
    _register(client)
    assert _login(client).status_code == 403
    uid = str(_user("sam@test.com").id)
    listed = {u["email"]: u for u in client.get("/api/admin/users", headers=H).json()}
    assert listed["sam@test.com"]["is_verified"] is False

    r = client.patch(f"/api/admin/users/{uid}", headers=H, json={"is_verified": True})
    assert r.status_code == 200 and r.json()["is_verified"] is True
    assert _login(client).status_code == 200


def test_admin_password_reset_enforces_rule_and_signs_user_out(client):
    H = _admin_headers(client)
    old, _ = _signed_in(client)
    uid = str(_user("sam@test.com").id)
    assert client.patch(f"/api/admin/users/{uid}", headers=H, json={"new_password": "admin"}).status_code == 422
    assert client.patch(f"/api/admin/users/{uid}", headers=H, json={"new_password": NEW_PW}).status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    assert _login(client, password=NEW_PW).status_code == 200


# ── create_admin.py ──────────────────────────────────────────────────────────


def _load_script(name):
    path = Path(__file__).resolve().parent.parent / "seeds" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"seed_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def create_admin(client, monkeypatch):
    monkeypatch.delenv("CHESSLOOP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("CHESSLOOP_ADMIN_PASSWORD", raising=False)
    return _load_script("create_admin")


def test_create_admin_from_env(client, create_admin, monkeypatch, capsys):
    monkeypatch.setenv("CHESSLOOP_ADMIN_EMAIL", "owner@test.com")
    monkeypatch.setenv("CHESSLOOP_ADMIN_PASSWORD", PW)
    assert create_admin.main([]) == 0
    out = capsys.readouterr().out
    assert "created" in out and PW not in out
    u = _user("owner@test.com")
    assert u.role == "admin" and u.is_verified and u.username == "admin"
    assert _login(client, "owner@test.com").status_code == 200


def test_create_admin_from_stdin(client, create_admin, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(PW + "\n"))
    assert create_admin.main(["--email", "owner@test.com", "--password-stdin"]) == 0
    assert _login(client, "owner@test.com").status_code == 200


def test_create_admin_prompts_in_a_terminal(client, create_admin, monkeypatch):
    answers = iter([PW, PW, PW, "something-else-entirely"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr(create_admin.getpass, "getpass", lambda prompt="": next(answers))
    assert create_admin.main(["--email", "owner@test.com"]) == 0
    assert _login(client, "owner@test.com").status_code == 200
    assert create_admin.main(["--email", "second@test.com", "--username", "second"]) == 2  # mismatch


def test_create_admin_update_keeps_password_unless_reset(client, create_admin, monkeypatch):
    monkeypatch.setenv("CHESSLOOP_ADMIN_EMAIL", "owner@test.com")
    monkeypatch.setenv("CHESSLOOP_ADMIN_PASSWORD", PW)
    assert create_admin.main([]) == 0

    monkeypatch.setenv("CHESSLOOP_ADMIN_PASSWORD", NEW_PW)
    assert create_admin.main([]) == 0
    assert _login(client, "owner@test.com", PW).status_code == 200

    assert create_admin.main(["--reset-password"]) == 0
    assert _login(client, "owner@test.com", PW).status_code == 401
    assert _login(client, "owner@test.com", NEW_PW).status_code == 200


def test_create_admin_promotes_and_verifies_existing_user(client, create_admin, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "email_verification", "on")
    _register(client)
    assert create_admin.main(["--email", "sam@test.com"]) == 0
    u = _user("sam@test.com")
    assert u.role == "admin" and u.is_verified


@pytest.mark.parametrize("args, env_pw", [
    ([], PW),                                            # no email
    (["--email", "not-an-email"], PW),                   # bad syntax
    (["--email", "owner@test.com"], "admin"),            # weak password
    (["--email", "owner@test.com"], "chessloop2026"),    # denylisted
    (["--email", "owner@test.com"], None),               # no password for a new admin
    (["--email", "owner@test.com", "--username", "ab"], PW),
])
def test_create_admin_validation_errors_exit_2(client, create_admin, monkeypatch, capsys, args, env_pw):
    if env_pw is not None:
        monkeypatch.setenv("CHESSLOOP_ADMIN_PASSWORD", env_pw)
    assert create_admin.main(args) == 2
    err = capsys.readouterr().err
    assert err.startswith("Error:")
    if env_pw:
        assert env_pw not in err


def test_create_admin_username_taken_exit_2(client, create_admin, monkeypatch):
    _register(client, "other@test.com", "admin")
    monkeypatch.setenv("CHESSLOOP_ADMIN_PASSWORD", PW)
    assert create_admin.main(["--email", "owner@test.com"]) == 2
    assert create_admin.main(["--email", "owner@test.com", "--username", "owner"]) == 0


def test_create_admin_db_error_exit_3(client, create_admin, monkeypatch, capsys):
    def boom():
        raise RuntimeError("disk is full")
    monkeypatch.setattr(create_admin, "init_db", boom)
    monkeypatch.setenv("CHESSLOOP_ADMIN_PASSWORD", PW)
    assert create_admin.main(["--email", "owner@test.com"]) == 3
    assert "disk is full" in capsys.readouterr().err


# ── Starter libraries without email ──────────────────────────────────────────


def test_seed_direct_is_idempotent_and_new_users_get_ruy_lopez(client):
    from models import Library
    from models.published_library import PublishedLibrary
    from services.starter_libraries import STARTERS, SEEDBOT_USER_ID, seed_starter_libraries

    with _session() as s:
        first = seed_starter_libraries(s, log=lambda *_: None)
    with _session() as s:
        second = seed_starter_libraries(s, log=lambda *_: None)
    assert first == {"created": len(STARTERS), "published": len(STARTERS), "skipped": 0, "lines_added": 0}
    assert second == {"created": 0, "published": 0, "skipped": len(STARTERS), "lines_added": 0}
    with _session() as s:
        assert len(s.exec(select(PublishedLibrary)).all()) == len(STARTERS)
        seedbot_libs = s.exec(select(Library).where(Library.owner_user_id == SEEDBOT_USER_ID)).all()
        assert len(seedbot_libs) == len(STARTERS)

    _register(client)
    H = {"Authorization": f"Bearer {_login(client).json()['access_token']}"}
    libs = client.get("/api/libraries", headers=H).json()
    assert [lib["name"] for lib in libs] == ["Ruy López — Closed"]
    # Discover lists them all
    listed = client.get("/api/public/libraries", headers=H).json()
    assert len(listed) == len(STARTERS)
    # F-055: opening a public library returns its lines (it used to be a 500)
    for lib in listed:
        r = client.get(f"/api/public/libraries/{lib['id']}/lines", headers=H)
        assert r.status_code == 200, lib["name"]
        assert 6 <= len(r.json()) <= 10 and all(x["name"] and not x["is_learned"] for x in r.json())


def test_seedbot_is_verified_hidden_and_cannot_log_in(client):
    from services.starter_libraries import SEEDBOT_EMAIL, seed_starter_libraries
    with _session() as s:
        seed_starter_libraries(s, log=lambda *_: None)
    u = _user(SEEDBOT_EMAIL)
    assert u.is_verified and u.role == "user" and u.password_hash.startswith("$2")
    for guess in ["", "SeedBot1234!", "seedbot"]:
        assert _login(client, SEEDBOT_EMAIL, guess).status_code in (401, 422)
    H = _admin_headers(client)
    assert SEEDBOT_EMAIL not in [x["email"] for x in client.get("/api/admin/users", headers=H).json()]


def test_seed_script_entry_point(client, capsys):
    script = _load_script("seed_libraries")
    assert script.main() == 0
    assert "Done:" in capsys.readouterr().out
    assert script.main() == 0
    assert "16 already there" in capsys.readouterr().out


# ── legacy_admin.py (the admin@example.com / "admin" account of old installs) ──


def _legacy_admin(**extra):
    from auth.password import hash_password
    from models import User
    with _session() as s:
        u = User(email="admin@example.com", username="admin", password_hash=hash_password("admin"),
                 role="admin", is_verified=False, **extra)
        s.add(u)
        s.commit()
        s.refresh(u)
        return u.id


def test_legacy_admin_report(client, capsys):
    script = _load_script("legacy_admin")
    assert script.main([]) == 0
    assert capsys.readouterr().out.split() == ["default_admin=0", "libraries=0", "other_admins=0"]
    _legacy_admin()
    _admin_headers(client)
    assert script.main([]) == 0
    assert capsys.readouterr().out.split() == ["default_admin=1", "libraries=0", "other_admins=1"]


def test_legacy_admin_changed_password_is_not_legacy(client, capsys):
    from auth.password import hash_password
    from models import User
    _legacy_admin()
    with _session() as s:
        u = s.exec(select(User).where(User.email == "admin@example.com")).first()
        u.password_hash = hash_password(NEW_PW)
        s.add(u)
        s.commit()
    script = _load_script("legacy_admin")
    assert script.main([]) == 0
    assert "default_admin=0" in capsys.readouterr().out
    assert script.main(["--delete"]) == 1
    assert _user("admin@example.com") is not None


def test_legacy_admin_delete(client):
    _legacy_admin()
    assert _load_script("legacy_admin").main(["--delete"]) == 0
    assert _user("admin@example.com") is None


def test_legacy_admin_with_libraries_is_locked_not_deleted(client):
    from auth.password import verify_password
    from models import Library
    uid = _legacy_admin()
    with _session() as s:
        s.add(Library(name="Old notes", color="white", owner_user_id=uid))
        s.commit()
    script = _load_script("legacy_admin")
    assert script.main(["--delete"]) == 1
    assert _user("admin@example.com") is not None
    assert script.main(["--lock"]) == 0
    u = _user("admin@example.com")
    assert u.role == "user" and u.token_version == 1
    assert not verify_password("admin", u.password_hash)
    with _session() as s:
        assert len(s.exec(select(Library).where(Library.owner_user_id == uid)).all()) == 1
