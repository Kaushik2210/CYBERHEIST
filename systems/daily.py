"""Daily challenge: one seeded run per calendar day, the same for every player."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from core.rng import GameRNG
from missions.mission_runner import Mission, MissionResult

DAILY_KEY = "daily"
CIPHERS = ("caesar", "vigenere", "substitution", "layered", "pattern", "hex")


def daily_seed(day: dt.date) -> int:
    """Seed for a calendar day, e.g. 2026-11-17 -> 20261117."""
    return int(day.strftime("%Y%m%d"))


def build_daily(day: dt.date) -> Mission:
    """Build the day's run: every challenge type, with the details drawn from the date's seed."""
    rng = GameRNG(daily_seed(day))
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
