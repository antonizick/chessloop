#!/usr/bin/env python3
"""
seed_libraries.py — load the 16 official starter opening libraries.

Run inside the backend container (works without email and without logging in):
    docker compose exec -T backend python seeds/seed_libraries.py

The libraries are written straight into the database, owned by a hidden
"seedbot" account that cannot log in, and published to Discover. New accounts
then receive a copy of "Ruy López — Closed". Running it again skips anything
already there.

Exit codes: 0 done, 3 database error.
"""
import os
import sys

# Running from /app/seeds — add /app so project modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import models  # noqa: F401,E402 — registers all SQLModel tables
from database import engine, init_db  # noqa: E402
from services.starter_libraries import seed_starter_libraries  # noqa: E402
from sqlmodel import Session  # noqa: E402


def main() -> int:
    print("Loading ChessLoop starter libraries…")
    try:
        init_db()
        with Session(engine) as session:
            counts = seed_starter_libraries(session)
    except Exception as e:  # lucent: any DB failure is reported, not a traceback
        print(f"Error: could not write to the database: {e}", file=sys.stderr)
        return 3
    print(
        f"\nDone: {counts['created']} created, {counts['published']} published, "
        f"{counts['skipped']} already there."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
