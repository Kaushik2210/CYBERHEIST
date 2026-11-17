"""The player's hacker profile."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core.progression import level_for_xp, title_for_level, xp_to_next

ALIAS_RE = re.compile(r"^[A-Za-z0-9_\-]{3,16}$")


def validate_alias(alias: str) -> str | None:
    """Return an error message for an invalid alias, or None when it is valid."""
    alias = alias.strip()
    if len(alias) < 3:
        return "Alias must be at least 3 characters."
    if len(alias) > 16:
        return "Alias must be at most 16 characters."
    if not ALIAS_RE.match(alias):
        return "Use letters, digits, '_' or '-' only."
    return None


@dataclass
class Player:
    """Persistent profile data for one hacker identity."""

    alias: str
    xp: int = 0
    credits: int = 0
    reputation: int = 0
    missions_completed: int = 0
    successes: int = 0
    failures: int = 0
    play_ticks: float = 0.0
    play_seconds: float = 0.0
    last_seed: int = 0
    created_at: str = ""
    level: int = field(default=1)

    def refresh_level(self, thresholds: list[int]) -> bool:
        """Recompute level from XP. Returns True if the player levelled up."""
        new = level_for_xp(self.xp, thresholds)
        up = new > self.level
        self.level = new
        return up

    def add_xp(self, amount: int, thresholds: list[int]) -> bool:
        """Grant XP (never negative). Returns True on level-up."""
        self.xp += max(0, int(amount))
        return self.refresh_level(thresholds)

    def add_credits(self, amount: int) -> None:
        """Add (or, with a negative amount, remove) credits, never below zero."""
        self.credits = max(0, self.credits + int(amount))

    def adjust_reputation(self, amount: int) -> None:
        """Change reputation, clamped to 0..1000."""
        self.reputation = max(0, min(1000, self.reputation + int(amount)))

    def record_success(self, first_clear: bool) -> None:
        """Count a successful infiltration."""
        self.successes += 1
        if first_clear:
            self.missions_completed += 1

    def record_failure(self) -> None:
        """Count a failed infiltration."""
        self.failures += 1

    def title(self, titles: list[str]) -> str:
        """Current rank title."""
        return title_for_level(self.level, titles)

    def xp_to_next(self, thresholds: list[int]) -> int | None:
        """XP needed for the next rank."""
        return xp_to_next(self.xp, thresholds)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Player":
        """Build a Player from a dict, ignoring unknown keys."""
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)
