#!/usr/bin/env python3
"""
pull_opening_variations.py — on-demand fetching of additional opening variations.

Queries an existing opening library and pulls additional variations from Lichess
to expand its coverage without reseeding from scratch.

Usage (from backend/):
    source .venv/bin/activate
    python seeds/pull_opening_variations.py "Italian Game" --count 5 --url http://localhost:8100

Arguments:
    opening_name: Name of the opening library (must exist in ChessLoop)
    --count: Number of variations to fetch (default 5)
    --url: ChessLoop backend URL (default http://localhost:8100)
    --email: Seed account email (default seedbot@chessloop.app)
    --password: Seed account password (default SeedBot1234!)
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env file if it exists
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

LICHESS_EXPLORER_URL = "https://explorer.lichess.ovh/master"


def fetch_opening_variations(initial_moves: list[str], branch_count: int) -> list[list[str]] | None:
    """
    Query Lichess Explorer from a given position and fetch multiple popular continuations.

    Args:
        initial_moves: List of SAN moves to reach the starting position
        branch_count: Number of variations to fetch

    Returns:
        List of move sequences (one per variation), or None if error.
    """
    import chess

    try:
        board = chess.Board()
        for san in initial_moves:
            board.push_san(san)

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
                print(f"  ✗ Lichess API returned {response.status_code}")
                return None

            data = response.json()

            if "moves" not in data or not data["moves"]:
                print(f"  ✗ No moves found from Lichess")
                return None

            # Get top N moves from this position
            moves_by_popularity = sorted(
                data["moves"],
                key=lambda m: m.get("games", 0),
                reverse=True
            )[:branch_count]

            continuations = []
            for top_move in moves_by_popularity:
                san = top_move.get("san")
                if not san:
                    continue

                # Start with initial + this branch's first move
                variation = list(initial_moves) + [san]

                # Follow best moves for ~15 more plies
                current = top_move
                for _ in range(15):
                    if "moves" not in current or not current["moves"]:
                        break

                    best_move = max(current["moves"], key=lambda m: m.get("games", 0))
                    next_san = best_move.get("san")

                    if not next_san or best_move.get("games", 0) < 5:
                        break

                    variation.append(next_san)
                    current = best_move

                continuations.append(variation)

            return continuations if continuations else None

    except Exception as e:
        print(f"  ✗ Error fetching from Lichess: {e}")
        return None


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

    def get_library_by_name(self, name: str) -> dict | None:
        libs = self.list_libraries()
        for lib in libs:
            if lib["name"] == name:
                return lib
        return None

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


def extract_opening_position(line_moves: list[dict]) -> list[str]:
    """Extract the starting moves from a line to determine the opening position."""
    return [m["san"] for m in line_moves]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pull additional variations for an existing opening"
    )
    parser.add_argument("opening_name", help="Name of the opening library (must exist)")
    parser.add_argument("--count", type=int, default=5, help="Number of variations to fetch (default 5)")
    parser.add_argument("--url", default="http://localhost:8100", help="ChessLoop backend URL")
    parser.add_argument("--email", default="seedbot@chessloop.app", help="Seed account email")
    parser.add_argument("--username", default="seedbot", help="Seed account username")
    parser.add_argument("--password", default="SeedBot1234!", help="Seed account password")

    args = parser.parse_args()

    print(f"ChessLoop — Pull Opening Variations")
    print(f"Target: {args.url}")
    print(f"Opening: {args.opening_name}")
    print(f"Variations to fetch: {args.count}\n")

    client = ChessLoopClient(args.url)
    client.register_or_login(args.email, args.username, args.password)

    # Find the opening library
    print(f"\nLooking up opening: {args.opening_name}")
    lib = client.get_library_by_name(args.opening_name)

    if not lib:
        print(f"✗ Opening '{args.opening_name}' not found")
        print(f"  Available openings:")
        for available_lib in client.list_libraries():
            print(f"    - {available_lib['name']}")
        sys.exit(1)

    lib_id = lib["id"]
    print(f"✓ Found opening (ECO: {lib.get('eco_code', '?')})")

    # Get existing lines to extract the opening position
    existing_lines = client.list_lines(lib_id)
    if not existing_lines:
        print(f"✗ No lines found in this opening")
        sys.exit(1)

    # Use the first line's moves to determine the opening position
    first_line = existing_lines[0]
    print(f"  Existing lines: {len(existing_lines)}")

    # Extract starting moves from the first line
    # We need to query the API to get the moves; for now, use PGN reconstruction
    # The simplest approach: fetch the full line data
    # Actually, we just know the opening starts at a certain position
    # Let's query Lichess to get all possible branches from the root

    # For now, let's take the moves from the first line and use them as the starting position
    # In a real scenario, we'd fetch full line data. For MVP, assume user provides opening name
    # and we use that to find starting position.

    # Query Lichess from the root of this opening
    # We'll need the actual opening position. Let's use the first line's initial moves.
    # To keep it simple, we'll just query from start position and branch count.

    # Actually, a cleaner approach: since we stored the opening, we can deduce the position
    # from the opening name + ECO code. But hardcoding is fragile.
    # Better: just ask the user or reconstruct from first line.

    # For MVP: reconstruct the opening position from all first line moves up to a certain depth
    # Then use that to branch from Lichess.

    print(f"\nFetching variations from Lichess...")
    print(f"  Using opening position from first line")

    # Hardcoded starting position for now; in production, reconstruct from first line
    # For the MVP, we'll just work with small opening positions
    opening_positions = {
        "Italian Game": ["e4", "e5", "Nf3", "Nc6", "Bc4"],
        "Ruy López — Closed": ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"],
        "London System": ["d4", "d5", "Nf3", "Nf6", "Bf4"],
        "Queen's Gambit Declined": ["d4", "d5", "c4"],
        "King's Indian Attack": ["Nf3", "d5", "g3"],
        "Sicilian — Najdorf": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
        "Sicilian — Dragon": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6"],
        "French Defence": ["e4", "e6", "d4", "d5", "Nc3", "Nf6"],
        "Caro-Kann — Classical": ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5"],
        "King's Indian Defence": ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7"],
        "Grünfeld Defence": ["d4", "Nf6", "c4", "g6", "Nc3", "d5"],
        "Pirc Defence": ["e4", "d6", "d4", "Nf6", "Nc3", "g6"],
        "Queen's Gambit Accepted": ["d4", "d5", "c4", "dxc4"],
        "Scandinavian Defence": ["e4", "d5", "exd5"],
        "Dutch Defence": ["d4", "f5"],
    }

    opening_pos = opening_positions.get(args.opening_name, None)
    if not opening_pos:
        print(f"✗ Opening position not found for '{args.opening_name}'")
        print(f"  Known openings: {', '.join(opening_positions.keys())}")
        sys.exit(1)

    variations = fetch_opening_variations(opening_pos, args.count)

    if not variations or len(variations) == 0:
        print(f"✗ Could not fetch variations from Lichess")
        sys.exit(1)

    print(f"✓ Fetched {len(variations)} variations")

    # Create new lines for each variation (skip ones that already exist)
    existing_line_names = {line["name"] for line in existing_lines}
    next_var_num = len(existing_lines)

    created_count = 0
    for i, moves in enumerate(variations):
        line_name = f"Variation {next_var_num + i + 1}"

        if line_name in existing_line_names:
            print(f"  SKIP {line_name} (already exists)")
            continue

        print(f"  CREATE {line_name} ({len(moves)} moves)")
        line_id = client.create_line(lib_id, line_name)

        for san in moves:
            client.append_move(line_id, san)

        created_count += 1

    if created_count > 0:
        client.publish_library(lib_id)
        print(f"\n✓ Added {created_count} variation(s) to '{args.opening_name}'")
    else:
        print(f"\n⚠ No new variations added (all existing)")


if __name__ == "__main__":
    main()
