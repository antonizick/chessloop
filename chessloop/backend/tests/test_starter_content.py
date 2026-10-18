"""The bundled starter lines (services/starter_data.json) and how they are seeded."""
import json
from pathlib import Path

import chess
from sqlmodel import select

DATA = Path(__file__).resolve().parent.parent / "services" / "starter_data.json"
MIN_LINES, MAX_LINES = 6, 10
MIN_PLIES, MAX_PLIES = 8, 24


def _openings():
    return json.loads(DATA.read_text(encoding="utf-8"))["openings"]


def test_data_covers_exactly_the_starter_libraries():
    from services.starter_libraries import STARTERS
    assert sorted(_openings()) == sorted(o.name for o in STARTERS)
    assert len(STARTERS) == 16


def test_every_line_is_legal_and_well_formed():
    total = 0
    for name, entry in _openings().items():
        lines = entry["lines"]
        assert MIN_LINES <= len(lines) <= MAX_LINES, f"{name}: {len(lines)} lines"
        names = [ln["name"] for ln in lines]
        assert all(n.strip() for n in names), f"{name}: empty line name"
        assert len(set(names)) == len(names), f"{name}: duplicate line names"
        seen = set()
        base = entry["base"]
        for ln in lines:
            moves = ln["moves"]
            assert MIN_PLIES <= len(moves) <= MAX_PLIES, f"{name} / {ln['name']}: {len(moves)} plies"
            assert moves[: len(base)] == base, f"{name} / {ln['name']}: does not start with the opening's moves"
            assert tuple(moves) not in seen, f"{name} / {ln['name']}: duplicate line"
            seen.add(tuple(moves))
            board = chess.Board()
            for san in moves:
                board.push(board.parse_san(san))  # raises on an illegal move
            total += 1
    assert total >= 16 * MIN_LINES


def test_first_line_continues_the_line_older_versions_seeded():
    from services.starter_libraries import LEGACY_LINES
    data = _openings()
    assert sorted(LEGACY_LINES) == sorted(data)
    for name, legacy in LEGACY_LINES.items():
        first = data[name]["lines"][0]["moves"]
        assert first[: len(legacy)] == legacy, name


def test_seed_creates_all_lines_and_publishes_them(db):
    from models import Library, Line
    from models.published_library import PublishedLibrary, PublishedLine
    from services.starter_libraries import seed_starter_libraries, starter_lines
    seed_starter_libraries(db, log=lambda *_: None)
    wanted_total = sum(len(v) for v in starter_lines().values())
    assert len(db.exec(select(Line)).all()) == wanted_total
    assert len(db.exec(select(PublishedLine)).all()) == wanted_total
    for lib in db.exec(select(Library)).all():
        lines = db.exec(select(Line).where(Line.library_id == lib.id).order_by(Line.order_index)).all()
        assert [ln.name for ln in lines] == [n for n, _ in starter_lines()[lib.name]]
    assert len(db.exec(select(PublishedLibrary)).all()) == 16


def test_top_up_adds_missing_lines_once_and_keeps_everything_else(db):
    """An install made by an older version holds one line per library."""
    from models import Library, Line
    from models.published_library import PublishedLibrary, PublishedLine
    from services.starter_libraries import (
        LEGACY_LINES, _moves_json, ensure_seedbot, seed_starter_libraries, starter_lines,
    )
    from services.library_service import publish_snapshot
    from models.line import STARTING_FEN

    # Build the old state by hand: one legacy line each, published.
    seedbot = ensure_seedbot(db)
    snapshot_ids = {}
    for name, legacy in LEGACY_LINES.items():
        lib = Library(name=name, color="white", owner_user_id=seedbot.id)
        db.add(lib)
        db.flush()
        db.add(Line(library_id=lib.id, name="Main line", starting_fen=STARTING_FEN,
                    moves=_moves_json(legacy), order_index=0))
        db.commit()
        db.refresh(lib)
        snapshot_ids[name] = publish_snapshot(lib, seedbot.id, db).id
    # a hand-made extra line in one library (must survive)
    ruy = db.exec(select(Library).where(Library.name == "Ruy López — Closed")).one()
    custom = _moves_json(["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6"])
    db.add(Line(library_id=ruy.id, name="Exchange", starting_fen=STARTING_FEN, moves=custom, order_index=1))
    db.commit()

    first = seed_starter_libraries(db, log=lambda *_: None)
    wanted = starter_lines()
    assert first["created"] == 0 and first["published"] == 0
    # every wanted line is added, except where the old one-liner already is the first line
    already = sum(1 for n, v in wanted.items() if v[0][1] == LEGACY_LINES[n])
    assert first["lines_added"] == sum(len(v) for v in wanted.values()) - already
    second = seed_starter_libraries(db, log=lambda *_: None)
    assert second["lines_added"] == 0 and second["skipped"] == 16

    for lib in db.exec(select(Library)).all():
        lines = db.exec(select(Line).where(Line.library_id == lib.id)).all()
        got = {tuple(m["san"] for m in json.loads(ln.moves)) for ln in lines}
        extra = 1 if lib.name == "Ruy López — Closed" else 0
        assert len(lines) == len(wanted[lib.name]) + extra, lib.name
        assert {tuple(s) for _, s in wanted[lib.name]} <= got
        # the legacy one-liner became the longer first line, not a duplicate
        legacy = tuple(LEGACY_LINES[lib.name])
        assert legacy not in got or legacy in {tuple(s) for _, s in wanted[lib.name]}, lib.name
    assert any(ln.moves == custom for ln in db.exec(select(Line)).all())
    # snapshots kept their ids and now carry every line
    for snap in db.exec(select(PublishedLibrary)).all():
        assert snap.id == snapshot_ids[snap.name]
        n = len(db.exec(select(PublishedLine).where(PublishedLine.published_library_id == snap.id)).all())
        assert n == len(wanted[snap.name]) + (1 if snap.name == "Ruy López — Closed" else 0), snap.name
