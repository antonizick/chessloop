"""Production settings: the JWT secret check run by start.py, and the defaults
derived for email links and the sender address."""
import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest

from config import Settings, jwt_secret_problem

BACKEND = Path(__file__).resolve().parent.parent
# 44 characters, the shape of `openssl rand -base64 32` (built here so secret scanners stay quiet)
GOOD_SECRET = base64.b64encode(bytes(range(32))).decode()


@pytest.mark.parametrize("secret", [
    "",
    "   ",
    "replace-with-openssl-rand-base64-32",  # .env.example placeholder (F-024)
    "$(openssl rand -base64 32)",            # pasted from the old README (F-024)
    "`openssl rand -base64 32`",
    "change-me-in-production",              # old dev compose default
    "dev-secret-change-me",                 # config.py default
    "short-but-random-Q2x9",
])
def test_unsafe_jwt_secrets_are_refused(secret):
    assert jwt_secret_problem(secret)


def test_generated_jwt_secrets_are_accepted():
    assert jwt_secret_problem(GOOD_SECRET) is None
    # deploy.sh's fallback without openssl: 43 base64 characters with /+= removed
    assert jwt_secret_problem("a" * 43) is None


def test_start_py_exits_with_a_fix_for_the_placeholder():
    env = {**os.environ, "CHESSLOOP_JWT_SECRET": "replace-with-openssl-rand-base64-32"}
    r = subprocess.run([sys.executable, "start.py"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 1
    assert "will not start" in r.stderr
    assert "openssl rand -base64 32" in r.stderr


def _settings(**env):
    # _env_file=None: ignore a developer's backend/.env
    return Settings(_env_file=None, **env)


def test_frontend_url_defaults_to_localhost_and_the_public_port():
    assert _settings().frontend_url == "http://localhost:8090"
    assert _settings(public_port=8123).frontend_url == "http://localhost:8123"


def test_frontend_url_defaults_to_https_domain():
    assert _settings(domain="chess.example.org").frontend_url == "https://chess.example.org"


def test_explicit_frontend_url_wins_and_loses_its_trailing_slash():
    s = _settings(domain="chess.example.org", frontend_url="http://192.168.1.20:8090/")
    assert s.frontend_url == "http://192.168.1.20:8090"


def test_smtp_from_defaults_to_the_smtp_login_address():
    assert _settings(smtp_user="me@mail.example.org").smtp_from == "ChessLoop <me@mail.example.org>"


def test_smtp_from_falls_back_to_the_domain_then_local():
    assert _settings(smtp_user="apikey", domain="chess.example.org").smtp_from == "ChessLoop <no-reply@chess.example.org>"
    assert _settings().smtp_from == "ChessLoop <no-reply@chessloop.local>"


def test_explicit_smtp_from_is_kept():
    assert _settings(smtp_from="Club <club@example.org>", smtp_user="x@y.org").smtp_from == "Club <club@example.org>"


def test_blank_values_from_compose_mean_the_defaults(monkeypatch):
    # compose passes "${FRONTEND_URL:-}" etc., so unset .env keys arrive as ""
    for key in ("FRONTEND_URL", "DOMAIN", "SMTP_FROM", "CORS_ORIGINS", "LICHESS_API_TOKEN"):
        monkeypatch.setenv(f"CHESSLOOP_{key}", "")
    monkeypatch.setenv("CHESSLOOP_EMAIL_VERIFICATION", "auto")
    monkeypatch.setenv("CHESSLOOP_EMAIL_MX_CHECK", "false")
    s = _settings()
    assert s.frontend_url == "http://localhost:8090"
    assert s.cors_origin_list == []


def test_wildcard_cors_from_old_installers_is_ignored():
    # F-015: older deploy.sh wrote CORS_ORIGINS=*; with allow_credentials that lets any site call the API
    s = _settings(cors_origins="*")
    assert s.cors_origin_list == []
    assert s.cors_wildcard_ignored
    s = _settings(cors_origins="https://chess.example.org, *")
    assert s.cors_origin_list == ["https://chess.example.org"]


def test_explicit_cors_origins_are_kept():
    s = _settings(cors_origins="https://a.example.org,https://b.example.org")
    assert s.cors_origin_list == ["https://a.example.org", "https://b.example.org"]
    assert not s.cors_wildcard_ignored
