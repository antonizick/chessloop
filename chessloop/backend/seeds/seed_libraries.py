#!/usr/bin/env python3
"""
seed_libraries.py — load the 16 official starter opening libraries and their lines.

Run inside the backend container (works without email and without logging in):
    docker compose exec -T backend python seeds/seed_libraries.py

The libraries are written straight into the database, owned by a hidden
"seedbot" account that cannot log in, and published to Discover. New accounts
then receive a copy of "Ruy López — Closed". Running it again adds any line that
is missing (an update ships more lines) and skips everything else.

    python seeds/seed_libraries.py --top-up-only
only adds missing lines to starter libraries that are already there (what
"chessloop update" runs); on an install without them it does nothing.

Exit codes: 0 done, 3 database error.
"""
import os
import sys

# Running from /app/seeds — add /app so project modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import models  # noqa: F401,E402 — registers all SQLModel tables
from database import engine, init_db  # noqa: E402
from models import Library  # noqa: E402
from services.starter_libraries import SEEDBOT_USER_ID, seed_starter_libraries  # noqa: E402
from sqlmodel import Session, select  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    top_up_only = "--top-up-only" in (sys.argv[1:] if argv is None else argv)
    if not top_up_only:
        print("Loading ChessLoop starter libraries…")
    try:
        init_db()
        with Session(engine) as session:
            if top_up_only:
                has_starters = session.exec(
                    select(Library).where(Library.owner_user_id == SEEDBOT_USER_ID)
                ).first()
                if has_starters is None:
                    return 0
            counts = seed_starter_libraries(session, log=(lambda _msg: None) if top_up_only else print)
    except Exception as e:  # lucent: any DB failure is reported, not a traceback
        print(f"Error: could not write to the database: {e}", file=sys.stderr)
        return 3
    if top_up_only:
        if counts["lines_added"]:
            print(f"Added {counts['lines_added']} lines to the starter libraries.")
        return 0
    print(
        f"\nDone: {counts['created']} created, {counts['published']} published, "
        f"{counts['skipped']} already there."
    )
    if counts["lines_added"]:
        print(f"Added {counts['lines_added']} lines to the starter libraries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
