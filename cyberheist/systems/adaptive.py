"""Adaptive difficulty: nudge the setting after runs that were too hard or too easy."""
from __future__ import annotations

from cyberheist.systems.statistics import Statistics

ORDER = ("easy", "normal", "hard")
FAILS_TO_EASE = 2       # failures in a row before stepping down
WINS_TO_RAISE = 3       # clean wins in a row (peak detection under 40%) before stepping up


def suggest(current: str, stats: Statistics) -> str | None:
    """Return the difficulty to switch to, or None to stay.

    Steps down after repeated failures, up after a run of clean wins. Uses the
    'fail_streak' and 'clean_streak' counters kept by Statistics.
    """
    idx = ORDER.index(current) if current in ORDER else 1
    if stats["fail_streak"] >= FAILS_TO_EASE and idx > 0:
        return ORDER[idx - 1]
    if stats["clean_streak"] >= WINS_TO_RAISE and idx < len(ORDER) - 1:
        return ORDER[idx + 1]
    return None
