#!/usr/bin/env python3
"""
seed_libraries.py — populate ChessLoop with 16 official starter opening libraries.

Usage (from backend/):
    source .venv/bin/activate
    python seeds/seed_libraries.py [--url http://localhost:8100] [--email admin@example.com] [--password secret]

The script:
1. Registers (or logs in to) the given account
2. Creates the 16 starter libraries
3. Creates lines inside each library and records moves from embedded PGN data
4. Publishes each library so they appear in the Public Discovery page

If a library with the same name already exists for the user, it is skipped.
"""

import argparse
import sys
from dataclasses import dataclass, field

import httpx

# ── Starter opening data ──────────────────────────────────────────────────────
# Each entry: (name, color, eco_code, difficulty, description, [SAN move list])
# Move lists are the mainline of each opening, not the full tree.

@dataclass
class Opening:
    name: str
    color: str          # 'white' | 'black' | 'both'
    eco: str
    difficulty: str     # 'beginner' | 'intermediate' | 'advanced'
    description: str
    lines: list[list[str]] = field(default_factory=list)  # list of SAN lines


STARTERS: list[Opening] = [
    Opening(
        name="Italian Game — Main Line",
        color="white", eco="C50", difficulty="beginner",
        description="1.e4 e5 2.Nf3 Nc6 3.Bc4 — control the centre, develop bishops early.",
        lines=[
            ["e4", "e5", "Nf3", "Nc6", "Bc4"],
        ],
    ),
    Opening(
        name="Italian Game — Giuoco Piano",
        color="white", eco="C54", difficulty="beginner",
        description="After 3…Bc5 White plays 4.c3 and 5.d4 for a direct central fight.",
        lines=[
            ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d4", "exd4", "cxd4", "Bb4+", "Nc3"],
        ],
    ),
    Opening(
        name="Ruy López — Closed",
        color="white", eco="C84", difficulty="intermediate",
        description="3.Bb5 pressures Black's e5 pawn via the knight on c6. The closed system with 9.h3 is highly strategic.",
        lines=[
            ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3"],
        ],
    ),
    Opening(
        name="London System",
        color="white", eco="D02", difficulty="beginner",
        description="Bf4 + Nf3 + e3 — a solid, low-theory setup that works against almost anything.",
        lines=[
            ["d4", "d5", "Nf3", "Nf6", "Bf4", "e6", "e3", "Bd6", "Bg3", "O-O", "Nbd2"],
        ],
    ),
    Opening(
        name="Queen's Gambit Declined",
        color="white", eco="D30", difficulty="intermediate",
        description="After 1.d4 d5 2.c4 e6 White fights for the centre. Classical and deeply studied.",
        lines=[
            ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "h6", "Bh4"],
        ],
    ),
    Opening(
        name="King's Indian Attack",
        color="white", eco="A07", difficulty="intermediate",
        description="Nf3 + g3 + Bg2 + d3 + Nbd2 — a flexible system White can use against many Black setups.",
        lines=[
            ["Nf3", "d5", "g3", "Nf6", "Bg2", "c5", "O-O", "Nc6", "d3", "e5", "Nbd2"],
        ],
    ),
    Opening(
        name="Sicilian Defence — Najdorf",
        color="black", eco="B90", difficulty="advanced",
        description="The world's most popular opening. 5…a6 keeps options open and prevents Bb5.",
        lines=[
            ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
        ],
    ),
    Opening(
        name="Sicilian Defence — Dragon",
        color="black", eco="B70", difficulty="advanced",
        description="6…g6 leads to dynamic, imbalanced play. The fianchettoed bishop on g7 is Black's key weapon.",
        lines=[
            ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3", "Bg7", "f3", "O-O", "Qd2", "Nc6"],
        ],
    ),
    Opening(
        name="French Defence — Classical",
        color="black", eco="C11", difficulty="intermediate",
        description="1…e6 2…d5 — solid, counterattacking. The classical variation with 3.Nc3 Nf6 is rich in theory.",
        lines=[
            ["e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5", "Be7", "e5", "Nfd7", "Bxe7", "Qxe7", "f4"],
        ],
    ),
    Opening(
        name="Caro-Kann — Classical",
        color="black", eco="B18", difficulty="intermediate",
        description="1…c6 defends d5 solidly. The classical 4…Bf5 gives Black an active bishop outside the pawn chain.",
        lines=[
            ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6", "h4", "h6", "Nf3", "Nd7", "h5", "Bh7", "Bd3", "Bxd3", "Qxd3"],
        ],
    ),
    Opening(
        name="King's Indian Defence",
        color="black", eco="E62", difficulty="intermediate",
        description="g6 + Bg7 + d6 + Nf6 — Black allows White a big centre and counterattacks with …e5 or …c5.",
        lines=[
            ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "Nf3", "O-O", "g3", "d6", "Bg2", "Nc6"],
        ],
    ),
    Opening(
        name="Grünfeld Defence",
        color="black", eco="D70", difficulty="advanced",
        description="Black allows White a huge pawn centre (d4 + c4 + e4) then attacks it immediately with …d5 and …c5.",
        lines=[
            ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5", "e4", "Nxc3", "bxc3", "Bg7", "Nf3", "c5"],
        ],
    ),
    Opening(
        name="Pirc Defence",
        color="black", eco="B07", difficulty="intermediate",
        description="1…d6 2…Nf6 3…g6 — a hypermodern defence. Black invites White to build a centre, then undermines it.",
        lines=[
            ["e4", "d6", "d4", "Nf6", "Nc3", "g6", "Nf3", "Bg7", "Be2", "O-O", "O-O"],
        ],
    ),
    Opening(
        name="Queen's Gambit Accepted",
        color="black", eco="D20", difficulty="beginner",
        description="2…dxc4 accepts the gambit. Black gives up the pawn temporarily and aims for active piece play.",
        lines=[
            ["d4", "d5", "c4", "dxc4", "Nf3", "Nf6", "e3", "e6", "Bxc4", "c5", "O-O", "a6"],
        ],
    ),
    Opening(
        name="Dutch Defence",
        color="black", eco="A80", difficulty="intermediate",
        description="1…f5 — combative and unbalancing. Black fights for the e4 square from move one.",
        lines=[
            ["d4", "f5", "Nf3", "Nf6", "g3", "e6", "Bg2", "Be7", "O-O", "O-O", "c4", "d6"],
        ],
    ),
    Opening(
        name="Scandinavian Defence",
        color="black", eco="B01", difficulty="beginner",
        description="1…d5 immediately challenges White's e4 pawn. After 2.exd5 Qxd5 3.Nc3 Qa5 Black has easy development.",
        lines=[
            ["e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5", "d4", "Nf6", "Nf3", "Bf5", "Bc4", "e6"],
        ],
    ),
]


# ── HTTP client ───────────────────────────────────────────────────────────────

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
            # Login to get token
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
        """Append a move by SAN. The backend computes UCI + FEN automatically."""
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

def seed(client: ChessLoopClient) -> None:
    existing = {lib["name"] for lib in client.list_libraries()}

    for opening in STARTERS:
        if opening.name in existing:
            print(f"  SKIP  {opening.name} (already exists)")
            continue

        print(f"  CREATE {opening.name}")
        lib_id = client.create_library(
            name=opening.name,
            color=opening.color,
            eco=opening.eco,
            difficulty=opening.difficulty,
            description=opening.description,
        )

        for i, san_list in enumerate(opening.lines):
            line_name = f"Main line" if len(opening.lines) == 1 else f"Variation {i + 1}"
            line_id = client.create_line(lib_id, line_name)
            print(f"    Line: {line_name} ({len(san_list)} moves)")
            for san in san_list:
                client.append_move(line_id, san)

        client.publish_library(lib_id)
        print(f"    Published ✓")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed ChessLoop with starter opening libraries")
    parser.add_argument("--url",      default="http://localhost:8100", help="Backend base URL")
    parser.add_argument("--email",    default="seed@chessloop.local",  help="Seed account email")
    parser.add_argument("--username", default="seedbot",               help="Seed account username")
    parser.add_argument("--password", default="SeedBot1234!",          help="Seed account password")
    args = parser.parse_args()

    print(f"ChessLoop seed script — target: {args.url}")
    print(f"Account: {args.email} ({args.username})\n")

    client = ChessLoopClient(args.url)
    client.register_or_login(args.email, args.username, args.password)

    print("\nSeeding libraries…")
    seed(client)

    print("\nDone! Seeded up to 16 starter openings.")


if __name__ == "__main__":
    main()
