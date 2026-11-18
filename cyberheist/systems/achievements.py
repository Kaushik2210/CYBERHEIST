"""Achievements: progress is derived from statistics, unlocks are stored with a timestamp."""
from __future__ import annotations

import time
from dataclasses import dataclass

from cyberheist.systems.statistics import Statistics


@dataclass(frozen=True)
class Achievement:
    """One achievement: unlocked when ``stat`` reaches ``target``."""

    aid: str
    name: str
    desc: str
    stat: str
    target: int


ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement("first_breach", "First Breach", "Complete one mission.", "missions_won", 1),
    Achievement("ghost_mode", "Ghost Mode", "Complete a mission with zero detection.", "ghost_runs", 1),
    Achievement("cipher_master", "Cipher Master", "Solve 10 encryption puzzles.", "ciphers_solved", 10),
    Achievement("speed_demon", "Speed Demon", "Beat a mission's par ticks.", "speed_runs", 1),
    Achievement("digital_phantom", "Digital Phantom", "Complete five missions in a row without failing.",
                "best_streak", 5),
    Achievement("market_regular", "Black Market Regular", "Buy five items.", "items_bought", 5),
    Achievement("zero_day_legend", "Zero Day Legend", "Complete mission 10.", "mission10_clears", 1),
)
BY_ID = {a.aid: a for a in ACHIEVEMENTS}


class AchievementTracker:
    """Tracks unlocked achievements (id -> unlock time) and reports new ones."""

    def __init__(self, unlocked: dict[str, str] | None = None) -> None:
        """Restore saved unlocks; unknown ids are dropped."""
        self.unlocked: dict[str, str] = {k: v for k, v in (unlocked or {}).items() if k in BY_ID}

    @staticmethod
    def progress(a: Achievement, stats: Statistics) -> tuple[int, int]:
        """(current, target), with current capped at target."""
        return min(int(stats[a.stat]), a.target), a.target

    def evaluate(self, stats: Statistics) -> list[Achievement]:
        """Unlock everything whose target is met. Returns only the newly unlocked ones."""
        new = []
        for a in ACHIEVEMENTS:
            if a.aid not in self.unlocked and stats[a.stat] >= a.target:
                self.unlocked[a.aid] = time.strftime("%Y-%m-%d %H:%M")
                new.append(a)
        return new

    def rows(self, stats: Statistics) -> list[tuple[str, str, str, str]]:
        """Rows for the achievements screen: status, name, progress, description."""
        out = []
        for a in ACHIEVEMENTS:
            cur, tgt = self.progress(a, stats)
            status = "UNLOCKED" if a.aid in self.unlocked else "locked"
            out.append((status, a.name, f"{cur}/{tgt}", a.desc))
        return out

    def to_rows(self) -> dict[str, str]:
        """Copy for saving."""
        return dict(self.unlocked)


def notify(ui: object, new: list[Achievement]) -> None:
    """Print an unlock banner for each new achievement (and ring the bell if sound is on)."""
    for a in new:
        ui.box("ACHIEVEMENT UNLOCKED", [a.name, a.desc], role="ok")  # type: ignore[attr-defined]
        ui.alert()  # type: ignore[attr-defined]
