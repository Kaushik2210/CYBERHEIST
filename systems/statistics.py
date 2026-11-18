"""Lifetime statistics counters, saved as key/value rows."""
from __future__ import annotations

from typing import Mapping

KEYS = (
    "missions_attempted", "missions_won", "missions_failed", "streak", "best_streak",
    "ciphers_solved", "firewalls_cracked", "passwords_cracked", "networks_mapped", "escapes",
    "wrong_guesses", "items_bought", "items_used", "ticks_total", "ghost_runs", "speed_runs",
    "credits_earned", "highest_detection", "mission10_clears",
    "fail_streak", "clean_streak", "daily_runs", "daily_best",
)
CLEAN_PEAK = 40
STAGE_KEYS = {"cipher": "ciphers_solved", "firewall": "firewalls_cracked", "password": "passwords_cracked",
              "network": "networks_mapped", "escape": "escapes"}


class Statistics:
    """Counters for the dashboard and for achievement progress."""

    def __init__(self, rows: Mapping[str, float] | None = None) -> None:
        """Start from saved rows; unknown keys are ignored, missing ones start at zero."""
        self.values: dict[str, float] = {k: 0.0 for k in KEYS}
        for k, v in (rows or {}).items():
            if k in self.values:
                self.values[k] = max(0.0, float(v))

    def __getitem__(self, key: str) -> float:
        return self.values[key]

    def bump(self, key: str, amount: float = 1) -> None:
        """Increase a counter."""
        self.values[key] += amount

    def record_mission(self, mission_id: int, success: bool, ticks: float, par_ticks: float,
                       peak_detection: float, wrong_guesses: int, solved: Mapping[str, int],
                       items_used: int, credits_earned: int = 0) -> None:
        """Fold one finished mission (won or lost) into the counters."""
        v = self.values
        v["missions_attempted"] += 1
        v["ticks_total"] += ticks
        v["wrong_guesses"] += wrong_guesses
        v["items_used"] += items_used
        v["highest_detection"] = max(v["highest_detection"], peak_detection)
        for stage, n in solved.items():
            if stage in STAGE_KEYS:
                v[STAGE_KEYS[stage]] += n
        if success:
            v["missions_won"] += 1
            v["streak"] += 1
            v["fail_streak"] = 0
            v["clean_streak"] = v["clean_streak"] + 1 if peak_detection < CLEAN_PEAK else 0
            v["best_streak"] = max(v["best_streak"], v["streak"])
            v["credits_earned"] += credits_earned
            if peak_detection == 0:
                v["ghost_runs"] += 1
            if ticks < par_ticks:
                v["speed_runs"] += 1
            if mission_id == 10:
                v["mission10_clears"] += 1
        else:
            v["missions_failed"] += 1
            v["streak"] = 0
            v["fail_streak"] += 1
            v["clean_streak"] = 0

    def dashboard_rows(self) -> list[tuple[str, str]]:
        """Label/value pairs for the statistics screen."""
        v = self.values
        won, tried = int(v["missions_won"]), int(v["missions_attempted"])
        rate = f"{100 * won / tried:.0f}%" if tried else "-"
        return [
            ("Missions won / attempted", f"{won} / {tried} ({rate})"),
            ("Current / best no-fail streak", f"{int(v['streak'])} / {int(v['best_streak'])}"),
            ("Ciphers solved", str(int(v["ciphers_solved"]))),
            ("Firewalls cracked", str(int(v["firewalls_cracked"]))),
            ("Passwords recovered", str(int(v["passwords_cracked"]))),
            ("Networks mapped", str(int(v["networks_mapped"]))),
            ("Escapes", str(int(v["escapes"]))),
            ("Wrong guesses", str(int(v["wrong_guesses"]))),
            ("Ghost runs / speed runs", f"{int(v['ghost_runs'])} / {int(v['speed_runs'])}"),
            ("Items bought / used", f"{int(v['items_bought'])} / {int(v['items_used'])}"),
            ("Highest detection reached", f"{v['highest_detection']:.0f}%"),
            ("Total mission ticks", f"{v['ticks_total']:.0f}"),
            ("Credits earned", f"{int(v['credits_earned']):,}"),
            ("Daily runs / best daily score", f"{int(v['daily_runs'])} / {int(v['daily_best'])}"),
        ]

    def to_rows(self) -> dict[str, float]:
        """Copy for saving."""
        return dict(self.values)
