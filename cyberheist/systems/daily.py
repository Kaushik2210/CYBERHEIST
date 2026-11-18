"""Daily challenge: one seeded run per calendar day, the same for every player."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from cyberheist.core.rng import GameRNG
from cyberheist.missions.mission_runner import Mission, MissionResult

CIPHERS = ("caesar", "vigenere", "substitution", "layered", "pattern", "hex")

# Bump this whenever a change alters which puzzles a date produces (generators, solver,
# stage parameters). Each version gets its own seeds and its own score boards, so scores
# are only ever compared between players who faced the same puzzles.
# tests/test_replay.py fails with a reminder if generation changes without a bump.
DAILY_VERSION = 1
DAILY_KEY = f"daily-v{DAILY_VERSION}"


def daily_seed(day: dt.date) -> int:
    """Calendar key for a day, e.g. 2026-11-17 -> 20261117 (what the score board shows)."""
    return int(day.strftime("%Y%m%d"))


def run_seed(day: dt.date) -> int:
    """The seed a day's run is generated from: date plus puzzle version, e.g. 2026111701."""
    return daily_seed(day) * 100 + DAILY_VERSION


def build_daily(day: dt.date) -> Mission:
    """Build the day's run: every challenge type, with the details drawn from the run seed."""
    rng = GameRNG(run_seed(day))
    stages = [
        {"type": "network", "label": "Map the grid", "params": {"hidden": rng.randint(1, 2),
                                                                  "target": rng.choice(["DATABASE", "BACKUP"])}},
        {"type": "firewall", "label": "Perimeter lock", "params": {"pool": rng.randint(6, 7), "length": 4}},
        {"type": "cipher", "label": "Intercept", "params": {"kind": rng.choice(CIPHERS)}},
        {"type": "password", "label": "Admin account", "params": {"digits": rng.randint(2, 3)}},
        {"type": "escape", "label": "Exfiltration", "params": {"rounds": rng.randint(3, 4)}},
    ]
    return Mission(
        mid=0, title=f"Daily Challenge {day.isoformat()}", tier="Daily",
        intro="A fresh target every day. Everyone gets the same one.",
        briefing="Clear all five systems. Your best score for today is kept.",
        primary=["Clear all five stages"], optional=[], stages=stages,
        par_ticks=70, grace_ticks=60, max_ticks=260, reward_xp=0, reward_credits=0,
        completion="Daily run complete.", events=True)


@dataclass
class ScoreBreakdown:
    """How a run's score was reached."""

    total: int
    lines: list[tuple[str, int]]


def score_run(result: MissionResult, par_ticks: int, cfg: dict[str, Any] | None = None) -> ScoreBreakdown:
    """Score a finished run. Failed runs score 0."""
    if not result.success:
        return ScoreBreakdown(0, [("Run failed", 0)])
    lines = [("Base", 1000),
             ("Ticks over par x5", -5 * max(0, round(result.ticks - par_ticks))),
             ("Peak detection x4", -4 * round(result.peak)),
             ("Wrong guesses x30", -30 * result.wrong)]
    if result.ticks < par_ticks:
        lines.append(("Under par", 200))
    if result.ghost:
        lines.append(("Ghost run (zero detection)", 300))
    return ScoreBreakdown(max(0, sum(v for _, v in lines)), lines)
