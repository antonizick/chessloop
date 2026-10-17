"""
starter_libraries.py — the 16 official starter opening libraries, seeded
straight into the database (no HTTP, no email) and published to Discover.

New accounts get a copy of "Ruy López — Closed" at registration
(routers/auth.py), so that one must exist for the welcome clone to work.
Used by seeds/seed_libraries.py; safe to run any number of times.
"""
import json
import secrets
from dataclasses import dataclass, field
from uuid import UUID

import chess
from sqlmodel import Session, select

from auth.password import hash_password
from models import Library, Line, User
from models.line import STARTING_FEN
from models.published_library import PublishedLibrary
from services.library_service import publish_snapshot

# Owner of every seeded library. Hidden from Admin → Users and protected from
# edits there (routers/admin.py). It can never log in: its password is a random
# value that is hashed and thrown away.
SEEDBOT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
SEEDBOT_USERNAME = "seedbot"
SEEDBOT_EMAIL = "seedbot@chessloop.local"

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


def seed_starter_libraries(session: Session, log=print) -> dict:
    """Create and publish any missing starter library. Returns counts."""
    seedbot = ensure_seedbot(session)
    created = published = skipped = 0
    for opening in STARTERS:
        lib = session.exec(
            select(Library).where(Library.owner_user_id == seedbot.id, Library.name == opening.name)
        ).first()
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
            for i, san_list in enumerate(opening.lines):
                session.add(Line(
                    library_id=lib.id,
                    name="Main line" if len(opening.lines) == 1 else f"Variation {i + 1}",
                    starting_fen=STARTING_FEN,
                    moves=_moves_json(san_list),
                    order_index=i,
                ))
            session.commit()
            session.refresh(lib)
            created += 1
            log(f"  CREATE  {opening.name}")
        has_snapshot = session.exec(
            select(PublishedLibrary).where(PublishedLibrary.original_library_id == lib.id)
        ).first()
        if has_snapshot:
            skipped += 1
            log(f"  SKIP    {opening.name} (already published)")
            continue
        publish_snapshot(lib, seedbot.id, session)
        published += 1
        log(f"  PUBLISH {opening.name}")
    return {"created": created, "published": published, "skipped": skipped}
