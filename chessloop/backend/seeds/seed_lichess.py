#!/usr/bin/env python3
"""
seed_lichess.py — populate ChessLoop with opening libraries from Lichess Explorer API.

Fetches the top opening lines by ECO code from Lichess and creates ChessLoop libraries.

Usage (from backend/):
    source .venv/bin/activate
    export LICHESS_API_TOKEN='your_personal_token'
    python seeds/seed_lichess.py [--url http://localhost:8100]

Or use .env file (auto-loaded if LICHESS_API_TOKEN not in environment):
    Create backend/.env with: LICHESS_API_TOKEN=your_personal_token

The script:
1. Loads Lichess API token from LICHESS_API_TOKEN env var or .env file
2. Queries Lichess Explorer API for popular openings by FEN position
3. Extracts mainline moves from top master games
4. Registers/logs in to ChessLoop
5. Creates libraries and populates them with opening lines
6. Publishes libraries to Public Discovery

If a library with the same name already exists, it is skipped (idempotent).
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

# Load .env file if it exists (from backend/ directory)
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

LICHESS_API_TOKEN = os.getenv("LICHESS_API_TOKEN")
if not LICHESS_API_TOKEN:
    print("ERROR: LICHESS_API_TOKEN not found in environment or .env file")
    print("Set it via: export LICHESS_API_TOKEN='your_token'")
    print("Or create .env in backend/ directory with: LICHESS_API_TOKEN=your_token")
    sys.exit(1)

LICHESS_EXPLORER_URL = "https://explorer.lichess.ovh/master"

# ECO codes to seed — each specifies the opening name and initial moves to reach that opening
OPENINGS_TO_SEED = [
    # White e4 openings
    ("C50", "Italian Game", ["e4", "e5", "Nf3", "Nc6", "Bc4"], "white", "beginner"),
    ("C84", "Ruy López — Closed", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"], "white", "intermediate"),
    ("A07", "King's Indian Attack", ["Nf3", "d5", "g3"], "white", "intermediate"),
    ("D02", "London System", ["d4", "d5", "Nf3", "Nf6", "Bf4"], "white", "beginner"),
    ("D30", "Queen's Gambit Declined", ["d4", "d5", "c4"], "white", "intermediate"),
    # Black Sicilian openings
    ("B90", "Sicilian — Najdorf", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"], "black", "advanced"),
    ("B70", "Sicilian — Dragon", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6"], "black", "advanced"),
    # Black 1…e6
    ("C11", "French Defence", ["e4", "e6", "d4", "d5", "Nc3", "Nf6"], "black", "intermediate"),
    # Black 1…c6
    ("B18", "Caro-Kann — Classical", ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5"], "black", "intermediate"),
    # Black 1…Nf6 openings
    ("E62", "King's Indian Defence", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7"], "black", "intermediate"),
    ("D70", "Grünfeld Defence", ["d4", "Nf6", "c4", "g6", "Nc3", "d5"], "black", "advanced"),
    # Black 1…d6
    ("B07", "Pirc Defence", ["e4", "d6", "d4", "Nf6", "Nc3", "g6"], "black", "intermediate"),
    # Black 1…d5
    ("D20", "Queen's Gambit Accepted", ["d4", "d5", "c4", "dxc4"], "black", "beginner"),
    ("B01", "Scandinavian Defence", ["e4", "d5", "exd5"], "black", "beginner"),
    # Black 1…f5
    ("A80", "Dutch Defence", ["d4", "f5"], "black", "intermediate"),
]

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Opening:
    name: str
    color: str          # 'white' | 'black'
    eco: str
    difficulty: str     # 'beginner' | 'intermediate' | 'advanced'
    description: str
    lines: list[list[str]] = field(default_factory=list)  # list of SAN move sequences


# ── Lichess API client ────────────────────────────────────────────────────────

def fetch_opening_continuation(initial_moves: list[str]) -> list[str] | None:
    """
    Query Lichess Explorer from a given position and extend the opening with the most popular moves.

    Args:
        initial_moves: List of SAN moves to reach the starting position for this opening

    Returns:
        Extended list of SAN moves (initial + Lichess continuations), or None if error.
    """
    import chess

    try:
        # Build the position from initial moves
        board = chess.Board()
        for san in initial_moves:
            move = board.push_san(san)

        fen = board.fen()

        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{LICHESS_EXPLORER_URL}",
                params={
                    "fen": fen,
                    "since": 2020,
                    "until": 2026,
                    "speeds": "blitz,rapid,classical",
                    "ratings": "2000,2200,2400",
                },
            )

            if response.status_code != 200:
                print(f"    ⚠ Lichess API returned {response.status_code}")
                return initial_moves

            data = response.json()
            moves = list(initial_moves)

            # Follow the most popular moves for up to 15 additional moves
            current = data
            depth = 0
            max_continuation = 15

            while "moves" in current and current["moves"] and depth < max_continuation:
                # Pick the most popular move (highest games count)
                best_move = max(current["moves"], key=lambda m: m.get("games", 0))
                san = best_move.get("san")

                if not san or best_move.get("games", 0) < 10:  # Stop if move has too few games
                    break

                moves.append(san)
                current = best_move
                depth += 1

            return moves

    except Exception as e:
        print(f"    ✗ Error fetching from Lichess: {e}")
        return initial_moves


# ── ChessLoop HTTP client ─────────────────────────────────────────────────────

class ChessLoopClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.token: str | None = None
        self.http = httpx.Client(timeout=30)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def register_or_login(self, email: str, username: str, password: str) -> None:
        # Try register first; if 409 conflict, fall back to login
        r = self.http.post(
            f"{self.base}/api/auth/register",
            json={"email": email, "username": username, "password": password},
        )
        if r.status_code in (200, 201):
            print(f"Registered account: {username}")
        elif r.status_code == 409:
            print(f"Account exists, logging in as {email}")
        else:
            print(f"Register error {r.status_code}: {r.text}")
            sys.exit(1)

        r = self.http.post(
            f"{self.base}/api/auth/login",
            json={"email": email, "password": password},
        )
        if r.status_code != 200:
            print(f"Login error {r.status_code}: {r.text}")
            sys.exit(1)
        self.token = r.json()["access_token"]
        print("Authenticated ✓")

    def list_libraries(self) -> list[dict]:
        r = self.http.get(f"{self.base}/api/libraries", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_library(self, name: str, color: str, eco: str, difficulty: str, description: str) -> str:
        r = self.http.post(
            f"{self.base}/api/libraries",
            json={
                "name": name,
                "color": color,
                "eco_code": eco,
                "difficulty": difficulty,
                "description": description,
            },
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()["id"]

    def list_lines(self, lib_id: str) -> list[dict]:
        r = self.http.get(f"{self.base}/api/libraries/{lib_id}/lines", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_line(self, lib_id: str, name: str) -> str:
        r = self.http.post(
            f"{self.base}/api/libraries/{lib_id}/lines",
            json={"name": name},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()["id"]

    def append_move(self, line_id: str, san: str) -> None:
        r = self.http.post(
            f"{self.base}/api/lines/{line_id}/moves",
            json={"san": san},
            headers=self._headers(),
        )
        if r.status_code != 200:
            raise RuntimeError(f"append_move({san!r}) → {r.status_code}: {r.text}")

    def publish_library(self, lib_id: str) -> None:
        r = self.http.post(
            f"{self.base}/api/libraries/{lib_id}/publish",
            headers=self._headers(),
        )
        # 200 = published, 409 = already published — both are fine
        if r.status_code not in (200, 409):
            print(f"  Warning: publish returned {r.status_code}")


# ── Seed logic ────────────────────────────────────────────────────────────────

def seed_from_lichess(client: ChessLoopClient) -> None:
    """Fetch openings from Lichess and seed ChessLoop."""
    existing = {lib["name"] for lib in client.list_libraries()}

    for eco_code, opening_name, initial_moves, color, difficulty in OPENINGS_TO_SEED:
        if opening_name in existing:
            print(f"  SKIP  {opening_name} (already exists)")
            continue

        print(f"  FETCH {opening_name} ({eco_code})…")
        moves = fetch_opening_continuation(initial_moves)

        if not moves or moves == initial_moves:
            # Use initial moves if Lichess query failed or returned nothing
            moves = initial_moves
            print(f"    Using hardcoded mainline ({len(moves)} moves)")
        else:
            print(f"    Extended from Lichess ({len(moves)} moves total)")

        description = f"Popular opening from Lichess Explorer ({len(moves)} moves). ECO: {eco_code}. " \
                     f"Sourced from master games 2020–2026, rated 2000+."

        print(f"  CREATE {opening_name} ({len(moves)} moves, {color}, {difficulty})")
        lib_id = client.create_library(
            name=opening_name,
            color=color,
            eco=eco_code,
            difficulty=difficulty,
            description=description,
        )

        line_id = client.create_line(lib_id, "Main line")
        for san in moves:
            client.append_move(line_id, san)

        client.publish_library(lib_id)
        print(f"    Published ✓")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed ChessLoop from Lichess Explorer")
    parser.add_argument("--url",      default="http://localhost:8100", help="ChessLoop backend URL")
    parser.add_argument("--email",    default="seedbot@chessloop.app",  help="Seed account email")
    parser.add_argument("--username", default="seedbot",               help="Seed account username")
    parser.add_argument("--password", default="SeedBot1234!",           help="Seed account password")
    args = parser.parse_args()

    print(f"ChessLoop Lichess seed script")
    print(f"Target: {args.url}")
    print(f"Account: {args.email} ({args.username})")
    print(f"Lichess token: {'***' + LICHESS_API_TOKEN[-4:] if LICHESS_API_TOKEN else 'MISSING'}\n")

    client = ChessLoopClient(args.url)
    client.register_or_login(args.email, args.username, args.password)

    print("\nSeeding openings from Lichess…\n")
    seed_from_lichess(client)

    print("\nDone! Seeded up to 16 openings from Lichess Explorer.")


if __name__ == "__main__":
    main()
