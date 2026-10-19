#!/usr/bin/env python3
"""Create (or update) the ChessLoop admin account. There is no default admin.

The installer calls it right after the containers start, passing the password
on stdin so it never appears in the process list or shell history:

    printf '%s\\n' "$PASSWORD" | docker compose exec -T \\
        -e CHESSLOOP_ADMIN_EMAIL=you@example.com \\
        backend python seeds/create_admin.py --password-stdin

Inputs:
    CHESSLOOP_ADMIN_EMAIL     (or --email)     admin email, required
    CHESSLOOP_ADMIN_USERNAME  (or --username)  display name, default "admin"
    CHESSLOOP_ADMIN_PASSWORD  or --password-stdin   the password (never argv);
                              in a terminal with neither, it asks (typing is hidden)
    --reset-password          also set the password of an existing account

The admin is created verified (no email needed). If an account with that email
already exists it is made an admin and marked verified; its password changes
only with --reset-password, which also signs it out everywhere.

Exit codes: 0 created or updated, 2 invalid input, 3 database error.
"""
import argparse
import getpass
import os
import sys

# Running from /app/seeds — add /app so project modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from email_validator import EmailNotValidError, validate_email  # noqa: E402

import models  # noqa: F401,E402 — registers all SQLModel tables
from auth.password import hash_password  # noqa: E402
from auth.policy import password_problem  # noqa: E402
from database import engine, init_db  # noqa: E402
from models.user import User  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

EXIT_OK, EXIT_INVALID, EXIT_DB = 0, 2, 3


def _fail(code: int, message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return code


def _read_password(from_stdin: bool) -> str | None:
    if from_stdin:
        line = sys.stdin.readline()
        return line.rstrip("\r\n") if line else None
    return os.environ.get("CHESSLOOP_ADMIN_PASSWORD") or None


def _ask_password() -> str | None:
    """Prompt twice with hidden typing; None if the two entries differ."""
    print("Choose the admin password (at least 12 characters; typing is hidden).")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Same password again: ") != first:
        return None
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update the ChessLoop admin account.")
    parser.add_argument("--email", default=os.environ.get("CHESSLOOP_ADMIN_EMAIL", ""))
    parser.add_argument("--username", default=os.environ.get("CHESSLOOP_ADMIN_USERNAME", "admin"))
    parser.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    parser.add_argument("--reset-password", action="store_true",
                        help="set the password even if the account already exists")
    args = parser.parse_args(argv)

    if not args.email.strip():
        return _fail(EXIT_INVALID, "no admin email given. Set CHESSLOOP_ADMIN_EMAIL or pass --email.")
    try:
        # Syntax only: a self-hosted server may have no DNS, and nobody emails the admin.
        email = validate_email(args.email.strip(), check_deliverability=False).normalized
    except EmailNotValidError as e:
        return _fail(EXIT_INVALID, f"'{args.email}' is not a valid email address: {e}")
    username = args.username.strip()
    if not 3 <= len(username) <= 32:
        return _fail(EXIT_INVALID, "the username must be 3 to 32 characters.")

    password = _read_password(args.password_stdin)
    if password is None and not args.password_stdin and sys.stdin.isatty():
        password = _ask_password()
        if password is None:
            return _fail(EXIT_INVALID, "the two passwords did not match. Run the command again.")
    if password is not None:
        problem = password_problem(password)
        if problem:
            return _fail(EXIT_INVALID, problem)

    try:
        init_db()
        with Session(engine) as db:
            existing = db.exec(select(User).where(User.email == email)).first()
            if existing is None:
                if password is None:
                    return _fail(EXIT_INVALID, "no password given. Pipe it in with --password-stdin "
                                               "or set CHESSLOOP_ADMIN_PASSWORD.")
                taken = db.exec(select(User).where(User.username == username)).first()
                if taken:
                    return _fail(EXIT_INVALID, f"the username '{username}' is already used by "
                                               f"another account. Pass a different --username.")
                db.add(User(
                    email=email,
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                    is_verified=True,
                ))
                db.commit()
                print(f"Admin account created: {email} (sign in with this email address).")
                return EXIT_OK

            changes = []
            if existing.role != "admin":
                existing.role = "admin"
                changes.append("made admin")
            if not existing.is_verified:
                existing.is_verified = True
                changes.append("marked verified")
            if args.reset_password:
                if password is None:
                    return _fail(EXIT_INVALID, "--reset-password needs a password "
                                               "(--password-stdin or CHESSLOOP_ADMIN_PASSWORD).")
                existing.password_hash = hash_password(password)
                existing.token_version += 1
                changes.append("password reset")
            db.add(existing)
            db.commit()
            detail = ", ".join(changes) if changes else "already correct"
            print(f"Admin account updated: {email} ({detail}).")
            if password is not None and not args.reset_password:
                print("The existing password was kept. Add --reset-password to replace it.")
            return EXIT_OK
    except Exception as e:  # lucent: report DB problems in one line, not a traceback
        return _fail(EXIT_DB, f"could not write to the database: {e}")


if __name__ == "__main__":
    sys.exit(main())
