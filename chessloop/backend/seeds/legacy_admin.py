#!/usr/bin/env python3
"""Find and retire the default admin account of installs made before 2026-10.

Older versions of ChessLoop created admin@example.com with the password
"admin" (F-003). It could never sign in (it was unverified), but it is a
publicly known password on an admin account. deploy.sh's Update runs this:

    docker compose exec -T backend python seeds/legacy_admin.py            # report
    docker compose exec -T backend python seeds/legacy_admin.py --delete   # remove it
    docker compose exec -T backend python seeds/legacy_admin.py --lock     # keep its data, lock it

The report is one "key=value" per line:
    default_admin   1 if admin@example.com still has the password "admin"
    libraries       libraries that account owns (deleting it deletes them)
    other_admins    verified admin accounts other than that one

--delete removes the account the way Admin → Users does (only when it owns no
libraries, unless --force). --lock gives it a random password nobody knows,
signs it out and takes away the admin role, keeping its data.

Exit codes: 0 done, 1 nothing to do (no such account), 3 database error.
"""
import argparse
import os
import secrets
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import models  # noqa: F401,E402 — registers all SQLModel tables
from auth.password import hash_password, verify_password  # noqa: E402
from database import engine, init_db  # noqa: E402
from models import Library  # noqa: E402
from models.user import User  # noqa: E402
from sqlmodel import Session, func, select  # noqa: E402

LEGACY_EMAIL = "admin@example.com"
LEGACY_PASSWORD = "admin"


def find_legacy_admin(db: Session) -> User | None:
    """admin@example.com, but only while its password is still "admin"."""
    user = db.exec(select(User).where(User.email == LEGACY_EMAIL)).first()
    if user is None or not verify_password(LEGACY_PASSWORD, user.password_hash):
        return None
    return user


def report(db: Session) -> dict[str, int]:
    legacy = find_legacy_admin(db)
    libraries = 0
    if legacy is not None:
        libraries = db.exec(
            select(func.count()).select_from(Library).where(Library.owner_user_id == legacy.id)
        ).one()
    admins = select(func.count()).select_from(User).where(
        User.role == "admin", User.is_verified == True  # noqa: E712 — SQL expression
    )
    if legacy is not None:
        admins = admins.where(User.id != legacy.id)
    others = db.exec(admins).one()
    return {"default_admin": int(legacy is not None), "libraries": int(libraries), "other_admins": int(others)}


def delete_legacy(db: Session, force: bool = False) -> str:
    from routers.admin import delete_user  # the same clean-up as Admin → Users

    legacy = find_legacy_admin(db)
    if legacy is None:
        return "none"
    if not force and report(db)["libraries"] > 0:
        return "has-libraries"
    # delete_user refuses only to delete the acting admin; nobody is acting here.
    delete_user(user_id=legacy.id, session=db, admin=SimpleNamespace(id=None))
    return "deleted"


def lock_legacy(db: Session) -> str:
    legacy = find_legacy_admin(db)
    if legacy is None:
        return "none"
    legacy.password_hash = hash_password(secrets.token_urlsafe(32))
    legacy.token_version += 1
    legacy.role = "user"
    db.add(legacy)
    db.commit()
    return "locked"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--delete", action="store_true", help="remove the account")
    group.add_argument("--lock", action="store_true", help="random password, no admin role")
    parser.add_argument("--force", action="store_true", help="--delete even if it owns libraries")
    args = parser.parse_args(argv)
    try:
        init_db()
        with Session(engine) as db:
            if args.delete:
                result = delete_legacy(db, force=args.force)
            elif args.lock:
                result = lock_legacy(db)
            else:
                for key, value in report(db).items():
                    print(f"{key}={value}")
                return 0
    except Exception as e:  # report DB problems in one line, not a traceback
        print(f"Error: {e}", file=sys.stderr)
        return 3
    print(f"result={result}")
    if result == "has-libraries":
        print("The account owns libraries; use --lock to keep them, or --delete --force.", file=sys.stderr)
        return 1
    return 0 if result in ("deleted", "locked") else 1


if __name__ == "__main__":
    sys.exit(main())
