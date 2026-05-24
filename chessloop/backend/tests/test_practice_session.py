"""Tests for practice session orchestration: position seeding + selection."""
import random
from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from models import PracticePosition
from services.practice_session import (
    ensure_positions_for_library,
    select_next_position,
)
from services.position_key import canonical_position_key, active_color
from tests.conftest import make_library, make_line_with_moves


# A short Italian-game stub: e4 e5 Nf3 Nc6 — 4 plies
ITALIAN_OPENING = [
    {
        "san": "e4", "uci": "e2e4",
        "fen_after": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    },
    {
        "san": "e5", "uci": "e7e5",
        "fen_after": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2",
    },
    {
        "san": "Nf3", "uci": "g1f3",
        "fen_after": "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
    },
    {
        "san": "Nc6", "uci": "b8c6",
        "fen_after": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
    },
]


# ── Position seeding ─────────────────────────────────────────────────────────

def test_white_library_seeds_only_white_to_move_positions(db, user):
    """In a white repertoire, the user drills the moves WHERE WHITE IS TO MOVE."""
    lib = make_library(db, user, color="white")
    make_line_with_moves(db, lib, ITALIAN_OPENING)

    created = ensure_positions_for_library(db, user.id, lib)
    # White to move at plies 0 (start) and 2 (after 1...e5) → 2 positions
    assert created == 2

    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    indices = sorted(p.move_index for p in positions)
    assert indices == [0, 2]


def test_black_library_seeds_only_black_to_move_positions(db, user):
    lib = make_library(db, user, color="black")
    make_line_with_moves(db, lib, ITALIAN_OPENING)

    created = ensure_positions_for_library(db, user.id, lib)
    # Black to move at plies 1 and 3
    assert created == 2

    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    indices = sorted(p.move_index for p in positions)
    assert indices == [1, 3]


def test_both_library_seeds_every_position(db, user):
    lib = make_library(db, user, color="both")
    make_line_with_moves(db, lib, ITALIAN_OPENING)

    created = ensure_positions_for_library(db, user.id, lib)
    assert created == 4

    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    assert sorted(p.move_index for p in positions) == [0, 1, 2, 3]


def test_seeding_is_idempotent(db, user):
    lib = make_library(db, user, color="white")
    make_line_with_moves(db, lib, ITALIAN_OPENING)

    first = ensure_positions_for_library(db, user.id, lib)
    second = ensure_positions_for_library(db, user.id, lib)
    assert first == 2
    assert second == 0  # nothing new the second time

    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    assert len(positions) == 2


def test_position_key_uses_canonical_fen(db, user):
    lib = make_library(db, user, color="white")
    line = make_line_with_moves(db, lib, ITALIAN_OPENING)

    ensure_positions_for_library(db, user.id, lib)
    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id).order_by(PracticePosition.move_index)
    ).all()

    # First position: starting position (move_index=0), key = canonical of standard FEN
    expected_start = canonical_position_key(line.starting_fen)
    assert positions[0].position_key == expected_start
    # Verify no clock fields leaked in
    assert "0 1" not in positions[0].position_key

    # Second position: after 1.e4 1...e5, key = canonical of move 1's fen_after
    expected_after_e5 = canonical_position_key(ITALIAN_OPENING[1]["fen_after"])
    assert positions[1].position_key == expected_after_e5


def test_empty_line_creates_no_positions(db, user):
    lib = make_library(db, user, color="white")
    make_line_with_moves(db, lib, [])
    assert ensure_positions_for_library(db, user.id, lib) == 0


# ── Selection ────────────────────────────────────────────────────────────────

def test_select_returns_none_for_empty_user(db, user):
    assert select_next_position(db, user.id, "weakest", {}) is None


def test_leech_drill_returns_only_leeches(db, user):
    lib = make_library(db, user, color="white")
    make_line_with_moves(db, lib, ITALIAN_OPENING)
    ensure_positions_for_library(db, user.id, lib)

    # Mark one as a leech
    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    positions[0].is_leech = True
    positions[0].repetitions = 2
    db.commit()

    # Need active library for the mode's default scope
    rng = random.Random(0)
    picked = select_next_position(db, user.id, "leech_drill", {}, rng=rng)
    assert picked is not None
    assert picked.id == positions[0].id
    assert picked.is_leech is True


def test_leech_drill_returns_none_when_no_leeches(db, user):
    lib = make_library(db, user, color="white")
    make_line_with_moves(db, lib, ITALIAN_OPENING)
    ensure_positions_for_library(db, user.id, lib)
    assert select_next_position(db, user.id, "leech_drill", {}, rng=random.Random(0)) is None


def test_weakest_returns_new_items_when_none_due(db, user):
    """All positions are brand-new → should return one of them."""
    lib = make_library(db, user, color="white")
    make_line_with_moves(db, lib, ITALIAN_OPENING)
    ensure_positions_for_library(db, user.id, lib)
    # All positions have repetitions=0 → new

    picked = select_next_position(db, user.id, "weakest", {}, rng=random.Random(0))
    assert picked is not None
    assert picked.repetitions == 0


def test_weakest_prefers_due_over_far_future(db, user):
    """A position due now should be picked over one due 10 days from now."""
    lib = make_library(db, user, color="both")
    make_line_with_moves(db, lib, ITALIAN_OPENING)
    ensure_positions_for_library(db, user.id, lib)

    positions = db.exec(
        select(PracticePosition).where(PracticePosition.user_id == user.id)
    ).all()
    now = datetime.utcnow()
    # Three positions: not due (future). One: due now. All have reps > 0.
    for i, p in enumerate(positions):
        p.repetitions = 2
        p.due_at = now - timedelta(hours=1) if i == 2 else now + timedelta(days=10)
    db.commit()

    # Force 0% chance of picking new — but there are none anyway
    rng = random.Random(0)
    picked = select_next_position(db, user.id, "weakest", {}, now=now, rng=rng)
    assert picked is not None
    assert picked.id == positions[2].id


def test_weakest_only_considers_active_libraries(db, user):
    """Positions in an inactive library should not be returned by 'weakest'."""
    active_lib = make_library(db, user, color="white", name="Active")
    inactive_lib = make_library(db, user, color="white", name="Inactive")
    inactive_lib.is_active = False
    db.commit()

    make_line_with_moves(db, active_lib, ITALIAN_OPENING)
    make_line_with_moves(db, inactive_lib, ITALIAN_OPENING)
    ensure_positions_for_library(db, user.id, active_lib)
    ensure_positions_for_library(db, user.id, inactive_lib)

    # Pick 20 times — should never be from the inactive library
    active_lines = {l.id for l in [active_lib]}
    for _ in range(20):
        picked = select_next_position(db, user.id, "weakest", {}, rng=random.Random())
        assert picked is not None
        line = db.exec(
            select(__import__("models").Line).where(__import__("models").Line.id == picked.line_id)
        ).first()
        assert line.library_id == active_lib.id


def test_selected_mode_respects_library_scope(db, user):
    lib_a = make_library(db, user, color="white", name="A")
    lib_b = make_library(db, user, color="white", name="B")
    make_line_with_moves(db, lib_a, ITALIAN_OPENING)
    make_line_with_moves(db, lib_b, ITALIAN_OPENING)
    ensure_positions_for_library(db, user.id, lib_a)
    ensure_positions_for_library(db, user.id, lib_b)

    # Scope to lib_a only
    for _ in range(15):
        picked = select_next_position(
            db, user.id, "selected", {"library_ids": [str(lib_a.id)]}, rng=random.Random()
        )
        assert picked is not None
        line = db.exec(
            select(__import__("models").Line).where(__import__("models").Line.id == picked.line_id)
        ).first()
        assert line.library_id == lib_a.id


def test_active_color_helper():
    """Quick sanity for the FEN helper used by seeding."""
    assert active_color("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") == "white"
    assert active_color("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1") == "black"
