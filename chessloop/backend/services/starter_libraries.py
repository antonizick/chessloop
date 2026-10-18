"""
starter_libraries.py — the 16 official starter opening libraries, seeded
straight into the database (no HTTP, no email) and published to Discover.
Each library holds several named lines, bundled in starter_data.json (built
offline by scripts/build-starter-lines.py; nothing is fetched at run time).

New accounts get a copy of "Ruy López — Closed" at registration
(routers/auth.py), so that one must exist for the welcome clone to work.
Used by seeds/seed_libraries.py; safe to run any number of times.
"""
import json
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import chess
from sqlmodel import Session, select

from auth.password import hash_password
from models import Library, Line, User
from models.line import STARTING_FEN
from models.published_library import PublishedLibrary, PublishedLine
from services.library_service import publish_snapshot

# Owner of every seeded library. Hidden from Admin → Users and protected from
# edits there (routers/admin.py). It can never log in: its password is a random
# value that is hashed and thrown away.
SEEDBOT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
SEEDBOT_USERNAME = "seedbot"
SEEDBOT_EMAIL = "seedbot@chessloop.local"

# Older versions seeded ONE line per library. Those exact lines are replaced by the
# longer line that continues them (see _top_up_lines); nothing else is ever rewritten.
LEGACY_LINES: dict[str, list[str]] = {
    "Italian Game — Main Line": ["e4", "e5", "Nf3", "Nc6", "Bc4"],
    "Italian Game — Giuoco Piano": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d4", "exd4", "cxd4", "Bb4+", "Nc3"],
    "Ruy López — Closed": ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3"],
    "London System": ["d4", "d5", "Nf3", "Nf6", "Bf4", "e6", "e3", "Bd6", "Bg3", "O-O", "Nbd2"],
    "Queen's Gambit Declined": ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "h6", "Bh4"],
    "King's Indian Attack": ["Nf3", "d5", "g3", "Nf6", "Bg2", "c5", "O-O", "Nc6", "d3", "e5", "Nbd2"],
    "Sicilian Defence — Najdorf": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
    "Sicilian Defence — Dragon": ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3", "Bg7", "f3", "O-O", "Qd2", "Nc6"],
    "French Defence — Classical": ["e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5", "Be7", "e5", "Nfd7", "Bxe7", "Qxe7", "f4"],
    "Caro-Kann — Classical": ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6", "h4", "h6", "Nf3", "Nd7", "h5", "Bh7", "Bd3", "Bxd3", "Qxd3"],
    "King's Indian Defence": ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "Nf3", "O-O", "g3", "d6", "Bg2", "Nc6"],
    "Grünfeld Defence": ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5", "e4", "Nxc3", "bxc3", "Bg7", "Nf3", "c5"],
    "Pirc Defence": ["e4", "d6", "d4", "Nf6", "Nc3", "g6", "Nf3", "Bg7", "Be2", "O-O", "O-O"],
    "Queen's Gambit Accepted": ["d4", "d5", "c4", "dxc4", "Nf3", "Nf6", "e3", "e6", "Bxc4", "c5", "O-O", "a6"],
    "Dutch Defence": ["d4", "f5", "Nf3", "Nf6", "g3", "e6", "Bg2", "Be7", "O-O", "O-O", "c4", "d6"],
    "Scandinavian Defence": ["e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5", "d4", "Nf6", "Nf3", "Bf5", "Bc4", "e6"],
}


@dataclass
class Opening:
    name: str
    color: str          # 'white' | 'black' | 'both'
    eco: str
    difficulty: str     # 'beginner' | 'intermediate' | 'advanced'
    description: str


STARTERS: list[Opening] = [
    Opening(
        name="Italian Game — Main Line",
        color="white", eco="C50", difficulty="beginner",
        description="1.e4 e5 2.Nf3 Nc6 3.Bc4 — control the centre, develop bishops early.",
    ),
    Opening(
        name="Italian Game — Giuoco Piano",
        color="white", eco="C54", difficulty="beginner",
        description="After 3…Bc5 White plays 4.c3 and 5.d4 for a direct central fight.",
    ),
    Opening(
        name="Ruy López — Closed",
        color="white", eco="C84", difficulty="intermediate",
        description="3.Bb5 pressures Black's e5 pawn via the knight on c6. The closed system with 9.h3 is highly strategic.",
    ),
    Opening(
        name="London System",
        color="white", eco="D02", difficulty="beginner",
        description="Bf4 + Nf3 + e3 — a solid, low-theory setup that works against almost anything.",
    ),
    Opening(
        name="Queen's Gambit Declined",
        color="white", eco="D30", difficulty="intermediate",
        description="After 1.d4 d5 2.c4 e6 White fights for the centre. Classical and deeply studied.",
    ),
    Opening(
        name="King's Indian Attack",
        color="white", eco="A07", difficulty="intermediate",
        description="Nf3 + g3 + Bg2 + d3 + Nbd2 — a flexible system White can use against many Black setups.",
    ),
    Opening(
        name="Sicilian Defence — Najdorf",
        color="black", eco="B90", difficulty="advanced",
        description="The world's most popular opening. 5…a6 keeps options open and prevents Bb5.",
    ),
    Opening(
        name="Sicilian Defence — Dragon",
        color="black", eco="B70", difficulty="advanced",
        description="6…g6 leads to dynamic, imbalanced play. The fianchettoed bishop on g7 is Black's key weapon.",
    ),
    Opening(
        name="French Defence — Classical",
        color="black", eco="C11", difficulty="intermediate",
        description="1…e6 2…d5 — solid, counterattacking. The classical variation with 3.Nc3 Nf6 is rich in theory.",
    ),
    Opening(
        name="Caro-Kann — Classical",
        color="black", eco="B18", difficulty="intermediate",
        description="1…c6 defends d5 solidly. The classical 4…Bf5 gives Black an active bishop outside the pawn chain.",
    ),
    Opening(
        name="King's Indian Defence",
        color="black", eco="E62", difficulty="intermediate",
        description="g6 + Bg7 + d6 + Nf6 — Black allows White a big centre and counterattacks with …e5 or …c5.",
    ),
    Opening(
        name="Grünfeld Defence",
        color="black", eco="D70", difficulty="advanced",
        description="Black allows White a huge pawn centre (d4 + c4 + e4) then attacks it immediately with …d5 and …c5.",
    ),
    Opening(
        name="Pirc Defence",
        color="black", eco="B07", difficulty="intermediate",
        description="1…d6 2…Nf6 3…g6 — a hypermodern defence. Black invites White to build a centre, then undermines it.",
    ),
    Opening(
        name="Queen's Gambit Accepted",
        color="black", eco="D20", difficulty="beginner",
        description="2…dxc4 accepts the gambit. Black gives up the pawn temporarily and aims for active piece play.",
    ),
    Opening(
        name="Dutch Defence",
        color="black", eco="A80", difficulty="intermediate",
        description="1…f5 — combative and unbalancing. Black fights for the e4 square from move one.",
    ),
    Opening(
        name="Scandinavian Defence",
        color="black", eco="B01", difficulty="beginner",
        description="1…d5 immediately challenges White's e4 pawn. After 2.exd5 Qxd5 3.Nc3 Qa5 Black has easy development.",
    ),
]




def ensure_seedbot(session: Session) -> User:
    seedbot = session.get(User, SEEDBOT_USER_ID)
    if seedbot:
        return seedbot
    username, email = SEEDBOT_USERNAME, SEEDBOT_EMAIL
    taken = session.exec(
        select(User).where((User.username == username) | (User.email == email))
    ).first()
    if taken:  # a real account already uses the name; keep the seedbot distinct
        suffix = secrets.token_hex(4)
        username, email = f"seedbot-{suffix}", f"seedbot-{suffix}@chessloop.local"
    seedbot = User(
        id=SEEDBOT_USER_ID,
        username=username,
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="user",
        is_verified=True,
    )
    session.add(seedbot)
    session.commit()
    session.refresh(seedbot)
    return seedbot


def _moves_json(san_list: list[str]) -> str:
    board = chess.Board()
    out = []
    for san in san_list:
        move = board.parse_san(san)
        uci = move.uci()
        board.push(move)
        out.append({"san": san, "uci": uci, "fen_after": board.fen()})
    return json.dumps(out)


@lru_cache(maxsize=1)
def starter_lines() -> dict[str, list[tuple[str, list[str]]]]:
    """Library name -> [(line name, SAN moves)] from starter_data.json, in order."""
    data = json.loads((Path(__file__).with_name("starter_data.json")).read_text(encoding="utf-8"))
    return {
        name: [(ln["name"], ln["moves"]) for ln in entry["lines"]]
        for name, entry in data["openings"].items()
    }


def _line_sans(line: Line) -> list[str]:
    return [m["san"] for m in json.loads(line.moves)]


def _top_up_lines(session: Session, lib: Library, wanted: list[tuple[str, list[str]]]) -> int:
    """Add any starter line the library lacks (matched by moves). Returns how many
    lines were added or upgraded. A library's lines belong to the hidden seedbot:
    the only line ever rewritten is an old one-line starter that still holds exactly
    what an earlier version seeded (LEGACY_LINES); it becomes the longer line that
    continues it. Nothing is deleted. Copies users made keep what they had."""
    existing = session.exec(select(Line).where(Line.library_id == lib.id).order_by(Line.order_index)).all()
    have = {tuple(_line_sans(ln)): ln for ln in existing}
    legacy = LEGACY_LINES.get(lib.name)
    legacy_line = have.get(tuple(legacy)) if legacy else None
    if legacy_line is not None and tuple(legacy) in {tuple(sans) for _, sans in wanted}:
        legacy_line = None   # the old line is still a starter line: nothing to upgrade
    next_index = max((ln.order_index for ln in existing), default=-1) + 1
    changed = 0
    for i, (name, sans) in enumerate(wanted):
        if tuple(sans) in have:
            continue
        if legacy_line is not None and sans[: len(legacy)] == legacy:
            legacy_line.name, legacy_line.moves = name, _moves_json(sans)
            legacy_line.order_index = i
            session.add(legacy_line)
            have[tuple(sans)] = legacy_line
            legacy_line = None
        else:
            session.add(Line(
                library_id=lib.id, name=name, starting_fen=STARTING_FEN,
                moves=_moves_json(sans), order_index=next_index + i if existing else i,
            ))
        changed += 1
    session.commit()
    return changed


def _sync_snapshot(session: Session, lib: Library, snapshot: PublishedLibrary) -> None:
    """Bring the published snapshot's lines in line with the library, keeping the
    snapshot (and so its id) as it is."""
    lines = session.exec(select(Line).where(Line.library_id == lib.id)).all()
    published = {
        pl.original_line_id: pl
        for pl in session.exec(select(PublishedLine).where(PublishedLine.published_library_id == snapshot.id))
    }
    for ln in lines:
        pl = published.get(ln.id)
        if pl is None:
            session.add(PublishedLine(
                published_library_id=snapshot.id, original_line_id=ln.id, name=ln.name,
                starting_fen=ln.starting_fen, moves=ln.moves, order_index=ln.order_index,
            ))
        elif (pl.moves, pl.name, pl.order_index) != (ln.moves, ln.name, ln.order_index):
            pl.name, pl.moves, pl.order_index = ln.name, ln.moves, ln.order_index
            session.add(pl)
    session.commit()


def seed_starter_libraries(session: Session, log=print) -> dict:
    """Create, top up and publish the starter libraries. Safe to run any number of
    times: a second run changes nothing. Returns counts (lines_added counts lines
    added to libraries that already existed)."""
    seedbot = ensure_seedbot(session)
    created = published = skipped = lines_added = 0
    for opening in STARTERS:
        wanted = starter_lines()[opening.name]
        lib = session.exec(
            select(Library).where(Library.owner_user_id == seedbot.id, Library.name == opening.name)
        ).first()
        added = 0
        if lib is None:
            lib = Library(
                name=opening.name,
                color=opening.color,
                owner_user_id=seedbot.id,
                eco_code=opening.eco,
                difficulty=opening.difficulty,
                description=opening.description,
            )
            session.add(lib)
            session.flush()
            session.commit()
            session.refresh(lib)
            _top_up_lines(session, lib, wanted)
            created += 1
            log(f"  CREATE  {opening.name} ({len(wanted)} lines)")
        else:
            added = _top_up_lines(session, lib, wanted)
            lines_added += added
            if added:
                log(f"  ADD     {opening.name} (+{added} lines)")
        snapshot = session.exec(
            select(PublishedLibrary).where(PublishedLibrary.original_library_id == lib.id)
        ).first()
        if snapshot:
            if added:
                _sync_snapshot(session, lib, snapshot)
            else:
                skipped += 1
                log(f"  SKIP    {opening.name} (already complete)")
            continue
        publish_snapshot(lib, seedbot.id, session)
        published += 1
        log(f"  PUBLISH {opening.name}")
    return {"created": created, "published": published, "skipped": skipped, "lines_added": lines_added}
