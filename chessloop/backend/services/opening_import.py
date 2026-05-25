"""
opening_import.py — opening discovery, import, and variation-pulling service.

Used by admin API endpoints. All logic lives here so scripts and endpoints
share the same code path.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

import httpx
from sqlmodel import Session, select

from models.library import Library
from models.line import Line, STARTING_FEN

LICHESS_EXPLORER_URL = "https://explorer.lichess.ovh/master"


# ── ECO opening database ──────────────────────────────────────────────────────
# Format: (eco, name, color, difficulty, description, moves_san)
# Covers the 50 most common openings. Admins can import any of these.

ECO_DATABASE: list[dict] = [
    # ── 1.e4 e5 openings (White) ──────────────────────────────────────────────
    {"eco": "C50", "name": "Italian Game", "color": "white", "difficulty": "beginner",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Bc4"],
     "description": "1.e4 e5 2.Nf3 Nc6 3.Bc4 — control the centre, develop bishops early."},
    {"eco": "C54", "name": "Italian Game — Giuoco Piano", "color": "white", "difficulty": "beginner",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d4", "exd4", "cxd4", "Bb4+", "Nc3"],
     "description": "After 3…Bc5, White plays 4.c3 and 5.d4 for a direct central fight."},
    {"eco": "C55", "name": "Italian Game — Two Knights", "color": "white", "difficulty": "intermediate",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "d4", "exd4", "e5", "d5", "Bb5", "Ne4"],
     "description": "After 3…Nf6 White can enter sharp tactical play with 4.Ng5 or 4.d4."},
    {"eco": "C84", "name": "Ruy López — Closed", "color": "white", "difficulty": "intermediate",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3"],
     "description": "3.Bb5 pressures the e5 pawn via Nc6. The closed system with 9.h3 is deeply strategic."},
    {"eco": "C88", "name": "Ruy López — Marshall Attack", "color": "white", "difficulty": "advanced",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "O-O", "c3", "d5"],
     "description": "Black sacrifices a pawn with 15…d5 for long-lasting initiative. One of the most studied lines."},
    {"eco": "C42", "name": "Petrov's Defence", "color": "white", "difficulty": "intermediate",
     "moves": ["e4", "e5", "Nf3", "Nf6", "Nxe5", "d6", "Nf3", "Nxe4", "d4", "d5", "Bd3"],
     "description": "Black counters 2.Nf3 with 2…Nf6, aiming for symmetrical solidity. Solid but passive."},
    {"eco": "C44", "name": "Scotch Game", "color": "white", "difficulty": "beginner",
     "moves": ["e4", "e5", "Nf3", "Nc6", "d4", "exd4", "Nxd4", "Nf6", "Nxc6", "bxc6", "e5"],
     "description": "3.d4 opens the centre immediately. Favoured by Kasparov. Direct and forcing."},
    {"eco": "C46", "name": "Three Knights Game", "color": "white", "difficulty": "beginner",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Nc3", "g6", "d4", "exd4", "Nd5"],
     "description": "3.Nc3 keeps options open. Can transpose to Four Knights or veer into independent lines."},
    # ── 1.d4 openings (White) ─────────────────────────────────────────────────
    {"eco": "D02", "name": "London System", "color": "white", "difficulty": "beginner",
     "moves": ["d4", "d5", "Nf3", "Nf6", "Bf4", "e6", "e3", "Bd6", "Bg3", "O-O", "Nbd2"],
     "description": "Bf4 + Nf3 + e3 — solid, low-theory setup that works against almost anything."},
    {"eco": "D30", "name": "Queen's Gambit Declined", "color": "white", "difficulty": "intermediate",
     "moves": ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "h6", "Bh4"],
     "description": "After 1.d4 d5 2.c4 e6 White fights for the centre. Classical and deeply studied."},
    {"eco": "D35", "name": "Queen's Gambit Exchange", "color": "white", "difficulty": "intermediate",
     "moves": ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "cxd5", "exd5", "Bg5", "Be7", "e3", "c6", "Bd3"],
     "description": "cxd5 leads to a symmetrical pawn structure. White aims to exploit the minority attack on the queenside."},
    {"eco": "D00", "name": "Queen's Pawn — Trompowsky", "color": "white", "difficulty": "intermediate",
     "moves": ["d4", "Nf6", "Bg5", "Ne4", "Bf4", "c5", "f3", "Nf6", "dxc5"],
     "description": "2.Bg5 is the Trompowsky — an early pin avoiding main-line theory. Popular at club level."},
    {"eco": "A07", "name": "King's Indian Attack", "color": "white", "difficulty": "intermediate",
     "moves": ["Nf3", "d5", "g3", "Nf6", "Bg2", "c5", "O-O", "Nc6", "d3", "e5", "Nbd2"],
     "description": "Nf3 + g3 + Bg2 + d3 + Nbd2 — flexible system against many Black setups."},
    {"eco": "A10", "name": "English Opening", "color": "white", "difficulty": "intermediate",
     "moves": ["c4", "e5", "Nc3", "Nf6", "g3", "d5", "cxd5", "Nxd5", "Bg2", "Nb6"],
     "description": "1.c4 — a hypermodern flank opening. White avoids early pawn commitment and controls d5 from afar."},
    {"eco": "A20", "name": "English Opening — Symmetrical", "color": "white", "difficulty": "advanced",
     "moves": ["c4", "c5", "Nf3", "Nf6", "Nc3", "Nc6", "g3", "g6", "Bg2", "Bg7", "O-O", "O-O", "d4"],
     "description": "Both sides mirror — rich strategic battles. One of the deepest openings at top level."},
    # ── Sicilian (Black) ──────────────────────────────────────────────────────
    {"eco": "B90", "name": "Sicilian — Najdorf", "color": "black", "difficulty": "advanced",
     "moves": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
     "description": "The world's most popular opening. 5…a6 keeps options open and prevents Bb5."},
    {"eco": "B70", "name": "Sicilian — Dragon", "color": "black", "difficulty": "advanced",
     "moves": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3", "Bg7", "f3", "O-O", "Qd2", "Nc6"],
     "description": "6…g6 — the fianchettoed Bg7 is Black's key weapon. Wild double-edged play."},
    {"eco": "B80", "name": "Sicilian — Scheveningen", "color": "black", "difficulty": "advanced",
     "moves": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "e6", "Be3", "Be7", "f3", "Nc6"],
     "description": "5…e6 — flexible structure. Kasparov's favourite. Black keeps lots of central tension."},
    {"eco": "B30", "name": "Sicilian — Kan", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "c5", "Nf3", "e6", "d4", "cxd4", "Nxd4", "a6", "Nc3", "Qc7"],
     "description": "4…a6 is the Kan — very flexible. Black avoids Bb5 and keeps the d5 advance available."},
    {"eco": "B20", "name": "Sicilian — Alapin (2.c3)", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "c5", "c3", "d5", "exd5", "Qxd5", "d4", "Nf6", "Nf3", "Bg4"],
     "description": "White plays 2.c3 for a solid centre. Black responds with 2…d5 for counterplay."},
    # ── 1…e6 (Black) ─────────────────────────────────────────────────────────
    {"eco": "C11", "name": "French Defence — Classical", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5", "Be7", "e5", "Nfd7", "Bxe7", "Qxe7", "f4"],
     "description": "1…e6 2…d5 — solid, counterattacking. Classical variation 3.Nc3 Nf6 is rich in theory."},
    {"eco": "C02", "name": "French — Advance Variation", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "e6", "d4", "d5", "e5", "c5", "c3", "Nc6", "Nf3", "Bd7", "Be2"],
     "description": "3.e5 gains space. Black counterattacks with …c5 immediately to challenge the centre."},
    {"eco": "C10", "name": "French — Rubinstein", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "e6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Nd7", "Nf3", "Ngf6", "Nxf6+", "Nxf6"],
     "description": "3…dxe4 releases the tension immediately. Solid and practical — Rubinstein's idea."},
    # ── 1…c6 (Black) ─────────────────────────────────────────────────────────
    {"eco": "B18", "name": "Caro-Kann — Classical", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6", "h4", "h6", "Nf3", "Nd7", "h5", "Bh7", "Bd3", "Bxd3", "Qxd3"],
     "description": "1…c6 defends d5 solidly. 4…Bf5 gives Black an active bishop outside the pawn chain."},
    {"eco": "B12", "name": "Caro-Kann — Advance", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "c6", "d4", "d5", "e5", "Bf5", "Nf3", "e6", "Be2", "c5"],
     "description": "3.e5 — White gains space. Black develops the Bf5 outside the pawn chain, then attacks with …c5."},
    {"eco": "B16", "name": "Caro-Kann — Bronstein-Larsen", "color": "black", "difficulty": "advanced",
     "moves": ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Nf6", "Nxf6+", "gxf6"],
     "description": "4…Nf6 5.Nxf6+ gxf6 — Black recaptures with the g-pawn, creating a strong centre but weakened kingside."},
    # ── 1…Nf6 (Black) ────────────────────────────────────────────────────────
    {"eco": "E62", "name": "King's Indian Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "Nf3", "O-O", "g3", "d6", "Bg2", "Nc6"],
     "description": "g6 + Bg7 — Black allows White a big centre and counterattacks with …e5 or …c5."},
    {"eco": "E60", "name": "King's Indian — Sämisch", "color": "black", "difficulty": "advanced",
     "moves": ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "f3", "O-O", "Be3", "e5"],
     "description": "5.f3 is the Sämisch — aggressive and uncompromising. White fortifies e4 and plans a kingside attack."},
    {"eco": "D70", "name": "Grünfeld Defence", "color": "black", "difficulty": "advanced",
     "moves": ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5", "e4", "Nxc3", "bxc3", "Bg7", "Nf3", "c5"],
     "description": "Black sacrifices d5 and attacks White's centre with …c5. A deeply theoretical battle."},
    {"eco": "D85", "name": "Grünfeld — Exchange", "color": "black", "difficulty": "advanced",
     "moves": ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5", "e4", "Nxc3", "bxc3", "Bg7", "Bc4", "c5", "Ne2"],
     "description": "After the exchange, White builds a powerful centre. Black counters with …c5 and piece activity."},
    # ── 1…d5 (Black) ─────────────────────────────────────────────────────────
    {"eco": "D20", "name": "Queen's Gambit Accepted", "color": "black", "difficulty": "beginner",
     "moves": ["d4", "d5", "c4", "dxc4", "Nf3", "Nf6", "e3", "e6", "Bxc4", "c5", "O-O", "a6"],
     "description": "2…dxc4 accepts the gambit. Black gives up the pawn temporarily and aims for active play."},
    {"eco": "D06", "name": "Queen's Gambit — Albin Counter", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "d5", "c4", "e5", "dxe5", "d4", "Nf3", "Nc6", "Nbd2", "Qe7"],
     "description": "2…e5 — a sharp gambit counter. Black pushes a pawn to d4 and gets active counterplay."},
    {"eco": "B01", "name": "Scandinavian Defence", "color": "black", "difficulty": "beginner",
     "moves": ["e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5", "d4", "Nf6", "Nf3", "Bf5", "Bc4", "e6"],
     "description": "1…d5 immediately challenges e4. After 2.exd5 Qxd5 3.Nc3 Qa5 Black has easy development."},
    # ── 1…f5 / 1…d6 / 1…g6 (Black) ──────────────────────────────────────────
    {"eco": "A80", "name": "Dutch Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "f5", "Nf3", "Nf6", "g3", "e6", "Bg2", "Be7", "O-O", "O-O", "c4", "d6"],
     "description": "1…f5 — combative and unbalancing. Black fights for the e4 square from move one."},
    {"eco": "A90", "name": "Dutch — Stonewall", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "f5", "Nf3", "Nf6", "g3", "e6", "Bg2", "d5", "O-O", "c6", "c4", "Bd6"],
     "description": "The Stonewall: pawns on d5, e6, f5, c6. Solid blockade — Black aims at the kingside."},
    {"eco": "B07", "name": "Pirc Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "d6", "d4", "Nf6", "Nc3", "g6", "Nf3", "Bg7", "Be2", "O-O", "O-O"],
     "description": "1…d6 2…Nf6 3…g6 — hypermodern. Black invites White to build a centre, then undermines it."},
    {"eco": "B06", "name": "Modern Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["e4", "g6", "d4", "Bg7", "Nc3", "d6", "f4", "Nf6", "Nf3", "O-O"],
     "description": "1…g6 — Black delays …d5 and lets White overextend. Similar to Pirc but more flexible."},
    # ── Gambits ───────────────────────────────────────────────────────────────
    {"eco": "C57", "name": "Fried Liver Attack", "color": "white", "difficulty": "advanced",
     "moves": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5", "Nxd5", "Nxf7"],
     "description": "Nxf7 sacrifices the knight for a vicious king hunt. Tactical fireworks — memorise carefully."},
    {"eco": "C34", "name": "King's Gambit", "color": "white", "difficulty": "intermediate",
     "moves": ["e4", "e5", "f4", "exf4", "Nf3", "d6", "d4", "g5", "h4", "g4", "Ng5"],
     "description": "2.f4 — a romantic gambit. White sacrifices a pawn for rapid development and attacking chances."},
    {"eco": "D07", "name": "Chigorin Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "d5", "c4", "Nc6", "Nf3", "Bg4", "cxd5", "Bxf3", "gxf3", "Qxd5"],
     "description": "2…Nc6 — an offbeat defence. Black accepts a slightly awkward structure for active piece play."},
    {"eco": "A57", "name": "Benko Gambit", "color": "black", "difficulty": "advanced",
     "moves": ["d4", "Nf6", "c4", "c5", "d5", "b5", "cxb5", "a6", "bxa6", "Bxa6"],
     "description": "Black sacrifices a pawn for permanent queenside pressure. A favourite of dynamic players."},
    {"eco": "D40", "name": "Nimzo-Indian Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "e3", "O-O", "Bd3", "d5", "Nf3", "c5"],
     "description": "3…Bb4 pins the knight and prevents e4. Classical structure — aims to double White's pawns."},
    {"eco": "E20", "name": "Nimzo-Indian — Sämisch", "color": "black", "difficulty": "advanced",
     "moves": ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "a3", "Bxc3+", "bxc3", "O-O"],
     "description": "4.a3 forces the bishop to take. Black gets good pawn structure and lets White have the bishop pair."},
    {"eco": "E10", "name": "Queen's Indian Defence", "color": "black", "difficulty": "intermediate",
     "moves": ["d4", "Nf6", "c4", "e6", "Nf3", "b6", "g3", "Bb7", "Bg2", "Be7", "O-O", "O-O"],
     "description": "3…b6 — Black fianchettoes the Bb7 to control e4. Safe and strategic."},
    {"eco": "E60", "name": "Catalan Opening", "color": "white", "difficulty": "intermediate",
     "moves": ["d4", "Nf6", "c4", "e6", "Nf3", "d5", "g3", "Be7", "Bg2", "O-O", "O-O", "dxc4", "Qc2"],
     "description": "g3 + Bg2 combined with d4 + c4. White aims for long-term pressure on the queenside."},
]


def search_openings(query: str) -> list[dict]:
    """
    Search the ECO database for openings matching the query string.
    Case-insensitive match on name, ECO code, or description.
    """
    q = query.strip().lower()
    if not q:
        return ECO_DATABASE[:20]  # Return first 20 if no query

    results = []
    for entry in ECO_DATABASE:
        haystack = f"{entry['name']} {entry['eco']} {entry['description']}".lower()
        if q in haystack:
            results.append(entry)

    return results[:20]  # Cap at 20 results


def count_lichess_variations(moves: list[str]) -> int:
    """Count how many variations are available from Lichess for the given opening position."""
    import chess
    try:
        board = chess.Board()
        for san in moves:
            board.push_san(san)
        fen = board.fen()
        with httpx.Client(timeout=5) as client:
            response = client.get(
                LICHESS_EXPLORER_URL,
                params={"fen": fen, "since": 2020, "until": 2026, "speeds": "blitz,rapid,classical", "ratings": "2000,2200,2400"},
            )
            if response.status_code != 200:
                return 0
            data = response.json()
            moves_list = data.get("moves", [])
            return len(moves_list) if moves_list else 0
    except Exception:
        return 0


def fetch_lichess_variations(moves: list[str], count: int) -> list[list[str]] | None:
    """Fetch variation lines from Lichess for the given opening position."""
    import chess
    try:
        board = chess.Board()
        for san in moves:
            board.push_san(san)
        fen = board.fen()
        with httpx.Client(timeout=10) as client:
            response = client.get(
                LICHESS_EXPLORER_URL,
                params={"fen": fen, "since": 2020, "until": 2026, "speeds": "blitz,rapid,classical", "ratings": "2000,2200,2400"},
            )
            if response.status_code != 200:
                return None
            data = response.json()
            moves_list = data.get("moves", [])
            if not moves_list:
                return None
            # Get top N moves by popularity
            top_moves = sorted(moves_list, key=lambda m: m.get("games", 0), reverse=True)[:count]
            continuations = []
            for top_move in top_moves:
                san = top_move.get("san")
                if not san:
                    continue
                variation = list(moves) + [san]
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
    except Exception:
        return None


def opening_exists(name: str, user_id: UUID, session: Session) -> bool:
    """Check whether a library with this name already exists for the user."""
    result = session.exec(
        select(Library).where(
            Library.name == name,
            Library.owner_user_id == user_id,
        )
    ).first()
    return result is not None


def import_opening(
    eco: str,
    name: str,
    color: str,
    difficulty: str,
    description: str,
    moves: list[str],
    user_id: UUID,
    session: Session,
    owner_user_id: UUID | None = None,
) -> tuple[Library, str]:
    """
    Import an opening as a new Library + Line in ChessLoop.

    Returns (library, status) where status is 'created' or 'exists'.
    Raises ValueError if the moves are invalid.

    If owner_user_id is provided, use that instead of user_id for ownership
    (useful for seed libraries that should be owned by a system user).
    """
    import chess

    actual_owner = owner_user_id if owner_user_id is not None else user_id

    if opening_exists(name, actual_owner, session):
        existing = session.exec(
            select(Library).where(
                Library.name == name,
                Library.owner_user_id == actual_owner,
            )
        ).first()
        return existing, "exists"

    # Validate moves
    board = chess.Board()
    parsed_moves: list[tuple[str, str, str]] = []  # (san, uci, fen_after)
    for san in moves:
        try:
            move = board.parse_san(san)
            uci = move.uci()
            board.push(move)
            parsed_moves.append((san, uci, board.fen()))
        except Exception as e:
            raise ValueError(f"Invalid move {san!r}: {e}")

    # Build move JSON (same format the teaching router uses)
    moves_json = json.dumps([
        {"san": san, "uci": uci, "fen_after": fen_after}
        for san, uci, fen_after in parsed_moves
    ])

    # Create the library
    lib = Library(
        name=name,
        color=color,
        owner_user_id=actual_owner,
        is_active=True,
        is_public=False,
        eco_code=eco,
        difficulty=difficulty,
        description=description,
    )
    session.add(lib)
    session.flush()  # get the ID

    # Create the mainline
    line = Line(
        library_id=lib.id,
        name="Main line",
        starting_fen=STARTING_FEN,
        moves=moves_json,
        order_index=0,
    )
    session.add(line)
    session.commit()
    session.refresh(lib)
    return lib, "created"


def publish_library(lib_id: UUID, session: Session) -> Library:
    """Mark a library as public."""
    from datetime import datetime
    lib = session.get(Library, lib_id)
    if lib and not lib.is_public:
        lib.is_public = True
        lib.published_at = datetime.utcnow()
        session.add(lib)
        session.commit()
        session.refresh(lib)
    return lib


def get_all_libraries_for_user(user_id: UUID, session: Session) -> list[Library]:
    """Return all libraries owned by a user."""
    return session.exec(
        select(Library).where(Library.owner_user_id == user_id)
    ).all()


# ── Canonical 16 starter openings ────────────────────────────────────────────
# Format: (eco, name, initial_moves, color, difficulty)
# Used by both the seed script and the /admin/openings/seed endpoint.

STARTER_OPENINGS: list[tuple[str, str, list[str], str, str]] = [
    ("C50", "Italian Game",             ["e4","e5","Nf3","Nc6","Bc4"],                                               "white", "beginner"),
    ("C84", "Ruy López — Closed",       ["e4","e5","Nf3","Nc6","Bb5","a6"],                                          "white", "intermediate"),
    ("A07", "King's Indian Attack",     ["Nf3","d5","g3"],                                                            "white", "intermediate"),
    ("D02", "London System",            ["d4","d5","Nf3","Nf6","Bf4"],                                               "white", "beginner"),
    ("D30", "Queen's Gambit Declined",  ["d4","d5","c4"],                                                             "white", "intermediate"),
    ("B90", "Sicilian — Najdorf",       ["e4","c5","Nf3","d6","d4","cxd4","Nxd4","Nf6","Nc3","a6"],                  "black", "advanced"),
    ("B70", "Sicilian — Dragon",        ["e4","c5","Nf3","d6","d4","cxd4","Nxd4","Nf6","Nc3","g6"],                  "black", "advanced"),
    ("C11", "French Defence",           ["e4","e6","d4","d5","Nc3","Nf6"],                                            "black", "intermediate"),
    ("B18", "Caro-Kann — Classical",    ["e4","c6","d4","d5","Nc3","dxe4","Nxe4","Bf5"],                             "black", "intermediate"),
    ("E62", "King's Indian Defence",    ["d4","Nf6","c4","g6","Nc3","Bg7"],                                           "black", "intermediate"),
    ("D70", "Grünfeld Defence",         ["d4","Nf6","c4","g6","Nc3","d5"],                                            "black", "advanced"),
    ("B07", "Pirc Defence",             ["e4","d6","d4","Nf6","Nc3","g6"],                                            "black", "intermediate"),
    ("D20", "Queen's Gambit Accepted",  ["d4","d5","c4","dxc4"],                                                      "black", "beginner"),
    ("B01", "Scandinavian Defence",     ["e4","d5","exd5"],                                                           "black", "beginner"),
    ("A80", "Dutch Defence",            ["d4","f5"],                                                                  "black", "intermediate"),
]
