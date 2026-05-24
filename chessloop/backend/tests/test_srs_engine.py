"""Unit tests for the SM-2 spaced-repetition engine.

These verify the math exhaustively because a wrong coefficient anywhere here
schedules silently incorrectly — practice still "works" but at the wrong
cadence, and you'd never notice until retention drops.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from models.practice import PracticePosition
from services import srs_engine as srs


# ── Fixtures ────────────────────────────────────────────────────────────────

NOW = datetime(2026, 5, 24, 12, 0, 0)


def make_pos(
    *,
    ease=2.5,
    interval=0.0,
    repetitions=0,
    leech_count=0,
    is_leech=False,
    due_at=None,
):
    return PracticePosition(
        id=uuid4(),
        user_id=uuid4(),
        line_id=uuid4(),
        move_index=0,
        position_key="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -",
        ease_factor=ease,
        interval_days=interval,
        repetitions=repetitions,
        leech_count=leech_count,
        is_leech=is_leech,
        due_at=due_at or NOW,
    )


# ── Correct answers ─────────────────────────────────────────────────────────

def test_first_correct_sets_interval_to_one_day():
    p = make_pos(repetitions=0, interval=0.0)
    srs.apply_correct(p, ease=None, now=NOW)
    assert p.repetitions == 1
    assert p.interval_days == 1.0
    assert p.ease_factor == 2.5  # unchanged with neutral
    assert p.due_at == NOW + timedelta(days=1)
    assert p.last_reviewed == NOW


def test_second_correct_sets_interval_to_six_days():
    p = make_pos(repetitions=1, interval=1.0)
    srs.apply_correct(p, ease=None, now=NOW)
    assert p.repetitions == 2
    assert p.interval_days == 6.0
    assert p.due_at == NOW + timedelta(days=6)


def test_third_correct_multiplies_by_ease_factor():
    p = make_pos(repetitions=2, interval=6.0, ease=2.5)
    srs.apply_correct(p, ease=None, now=NOW)
    assert p.repetitions == 3
    assert p.interval_days == pytest.approx(6.0 * 2.5)  # 15.0
    assert p.due_at == NOW + timedelta(days=15.0)


def test_easy_increases_ease_and_extends_interval():
    p = make_pos(repetitions=2, interval=6.0, ease=2.0)
    srs.apply_correct(p, ease="easy", now=NOW)
    # ease bumped by 0.15
    assert p.ease_factor == pytest.approx(2.15)
    # base interval = 6 * 2.0 = 12, easy multiplier 1.3 → 15.6
    assert p.interval_days == pytest.approx(12.0 * 1.3)


def test_easy_caps_ease_at_2_5():
    p = make_pos(repetitions=2, interval=6.0, ease=2.45)
    srs.apply_correct(p, ease="easy", now=NOW)
    assert p.ease_factor == 2.5  # capped, not 2.60


def test_hard_decreases_ease_and_shortens_interval():
    p = make_pos(repetitions=2, interval=6.0, ease=2.0)
    srs.apply_correct(p, ease="hard", now=NOW)
    assert p.ease_factor == pytest.approx(1.85)
    # base = 6 * 2.0 = 12, hard multiplier 0.8 → 9.6
    assert p.interval_days == pytest.approx(12.0 * 0.8)


def test_hard_floors_ease_at_1_3():
    p = make_pos(repetitions=2, interval=6.0, ease=1.35)
    srs.apply_correct(p, ease="hard", now=NOW)
    assert p.ease_factor == pytest.approx(1.3)  # floored at 1.3


def test_invalid_ease_raises():
    p = make_pos()
    with pytest.raises(ValueError):
        srs.apply_correct(p, ease="medium")


# ── Wrong answers ───────────────────────────────────────────────────────────

def test_wrong_resets_repetitions_and_dampens_interval():
    p = make_pos(repetitions=3, interval=15.0, leech_count=0)
    srs.apply_wrong(p, now=NOW)
    assert p.repetitions == 0
    # 15.0 * 0.25 = 3.75 → max(1.0, 3.75) = 3.75
    assert p.interval_days == pytest.approx(3.75)
    assert p.leech_count == 1


def test_wrong_floors_interval_at_one_day():
    p = make_pos(repetitions=3, interval=2.0)
    srs.apply_wrong(p, now=NOW)
    # 2.0 * 0.25 = 0.5 → max(1.0, 0.5) = 1.0
    assert p.interval_days == 1.0


def test_wrong_requeues_in_ten_minutes():
    p = make_pos(repetitions=2, interval=6.0)
    srs.apply_wrong(p, now=NOW)
    assert p.due_at == NOW + timedelta(minutes=10)
    # Note: due_at overrides interval_days for *this* requeue — interval_days
    # is what'll be considered after the *next* correct review.


def test_wrong_does_not_mark_leech_below_threshold():
    p = make_pos(leech_count=3)
    srs.apply_wrong(p, now=NOW)
    assert p.leech_count == 4
    assert p.is_leech is True  # reaches threshold


def test_fourth_wrong_marks_leech():
    p = make_pos(leech_count=0)
    for i in range(1, 5):
        srs.apply_wrong(p, now=NOW + timedelta(minutes=i))
        if i < 4:
            assert p.is_leech is False, f"premature leech at count {i}"
    assert p.is_leech is True
    assert p.leech_count == 4


def test_leech_stays_leech_through_correct_answers():
    p = make_pos(leech_count=4, is_leech=True, repetitions=0)
    srs.apply_correct(p, ease=None, now=NOW)
    # is_leech remains True — leech designation is sticky for the drill UI
    assert p.is_leech is True


# ── Full lifecycle ───────────────────────────────────────────────────────────

def test_wrong_then_correct_cycle():
    """After failing, next correct should start fresh from interval=1 day."""
    p = make_pos(repetitions=4, interval=20.0)
    srs.apply_wrong(p, now=NOW)
    assert p.repetitions == 0
    srs.apply_correct(p, ease=None, now=NOW + timedelta(minutes=10))
    assert p.repetitions == 1
    assert p.interval_days == 1.0  # spec: reps==0 → 1 day, regardless of dampened value


def test_full_learning_curve_easy_path():
    """Brand-new card → 3 correct in a row, all easy. Tracks interval growth."""
    p = make_pos()
    srs.apply_correct(p, ease="easy", now=NOW)
    # reps=0 → interval=1, easy ×1.3 → 1.3
    assert p.repetitions == 1
    assert p.interval_days == pytest.approx(1.3)
    assert p.ease_factor == 2.5  # already at cap

    srs.apply_correct(p, ease="easy", now=NOW + timedelta(days=1))
    # reps=1 → interval=6, easy ×1.3 → 7.8
    assert p.repetitions == 2
    assert p.interval_days == pytest.approx(7.8)

    srs.apply_correct(p, ease="easy", now=NOW + timedelta(days=8))
    # reps=2 → interval = prev * ease = 7.8 * 2.5 = 19.5, easy ×1.3 → 25.35
    assert p.repetitions == 3
    assert p.interval_days == pytest.approx(7.8 * 2.5 * 1.3)


def test_ease_factor_drift_under_repeated_hard():
    """Repeated 'hard' grades should walk ease down toward the floor."""
    p = make_pos(repetitions=2, interval=6.0, ease=2.5)
    expected_eases = [2.35, 2.20, 2.05, 1.90, 1.75, 1.60, 1.45, 1.30, 1.30]
    for expected in expected_eases:
        srs.apply_correct(p, ease="hard", now=NOW)
        assert p.ease_factor == pytest.approx(expected), f"ease drift wrong: got {p.ease_factor}"
