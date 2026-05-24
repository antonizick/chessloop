"""Modified SM-2 spaced-repetition scheduler.

Pure functions over a PracticePosition. No DB access, no time.now() side
effects — the caller passes `now` so the algorithm is deterministic and
testable.

Algorithm (per the ChessLoop planning doc):

  On correct answer:
      reps == 0:  new_interval = FIRST_INTERVAL  (1 day)
      reps == 1:  new_interval = SECOND_INTERVAL (6 days)
      reps >= 2:  new_interval = prev_interval * ease_factor

      if ease == 'easy':  ease += 0.15 (capped at EASE_MAX);    interval *= 1.3
      if ease == 'hard':  ease -= 0.15 (floored at EASE_MIN);   interval *= 0.8

      repetitions += 1
      due_at = now + new_interval days
      interval_days = new_interval

  On wrong answer:
      interval_days = max(WRONG_FLOOR, interval_days * WRONG_DAMPEN)
      repetitions = 0
      leech_count += 1
      due_at = now + WRONG_REQUEUE_MIN minutes  (force a quick re-review)
      if leech_count >= LEECH_THRESHOLD: is_leech = True
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from models.practice import PracticePosition

# ── Algorithm constants (tunable) ────────────────────────────────────────────
EASE_INIT = 2.5
EASE_MIN = 1.3
EASE_MAX = 2.5
EASE_STEP = 0.15

FIRST_INTERVAL_DAYS = 1.0
SECOND_INTERVAL_DAYS = 6.0

EASY_MULTIPLIER = 1.3
HARD_MULTIPLIER = 0.8

WRONG_INTERVAL_DAMPEN = 0.25
WRONG_INTERVAL_FLOOR_DAYS = 1.0
WRONG_REQUEUE_MINUTES = 10

LEECH_THRESHOLD = 4

WEAKNESS_EASE_THRESHOLD = 1.8  # used by session selection, not SM-2 itself


def apply_correct(
    pos: PracticePosition,
    ease: Optional[str] = None,
    now: Optional[datetime] = None,
) -> PracticePosition:
    """Mutate `pos` for a correct answer. Returns the same object for chaining."""
    if ease not in (None, "easy", "hard"):
        raise ValueError(f"ease must be None, 'easy', or 'hard' — got {ease!r}")

    now = now or datetime.utcnow()

    if pos.repetitions == 0:
        new_interval = FIRST_INTERVAL_DAYS
    elif pos.repetitions == 1:
        new_interval = SECOND_INTERVAL_DAYS
    else:
        new_interval = pos.interval_days * pos.ease_factor

    if ease == "easy":
        pos.ease_factor = min(pos.ease_factor + EASE_STEP, EASE_MAX)
        new_interval *= EASY_MULTIPLIER
    elif ease == "hard":
        pos.ease_factor = max(pos.ease_factor - EASE_STEP, EASE_MIN)
        new_interval *= HARD_MULTIPLIER
    # else: neutral grade — ease unchanged, no multiplier

    pos.interval_days = new_interval
    pos.repetitions += 1
    pos.due_at = now + timedelta(days=new_interval)
    pos.last_reviewed = now
    return pos


def apply_wrong(
    pos: PracticePosition,
    now: Optional[datetime] = None,
) -> PracticePosition:
    """Mutate `pos` for a wrong answer. Returns the same object for chaining."""
    now = now or datetime.utcnow()

    # Dampen the recorded interval. On the next correct review repetitions
    # will be 0, so the spec's "interval = FIRST_INTERVAL" branch will
    # override this — but we preserve the dampened value for diagnostics
    # and any future scheduler revision.
    pos.interval_days = max(
        WRONG_INTERVAL_FLOOR_DAYS,
        pos.interval_days * WRONG_INTERVAL_DAMPEN,
    )
    pos.repetitions = 0
    pos.leech_count += 1
    pos.due_at = now + timedelta(minutes=WRONG_REQUEUE_MINUTES)
    pos.last_reviewed = now

    if pos.leech_count >= LEECH_THRESHOLD:
        pos.is_leech = True

    return pos
