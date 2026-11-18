"""XP, levels and mission reward maths."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def level_for_xp(xp: int, thresholds: list[int]) -> int:
    """Return the 1-based level reached with ``xp`` points."""
    level = 1
    for idx, need in enumerate(thresholds):
        if xp >= need:
            level = idx + 1
    return level


def xp_to_next(xp: int, thresholds: list[int]) -> int | None:
    """XP still needed for the next level, or None at max level."""
    for need in thresholds:
        if xp < need:
            return need - xp
    return None


def title_for_level(level: int, titles: list[str]) -> str:
    """Return the rank title for a level (clamped to the table)."""
    return titles[max(0, min(level, len(titles)) - 1)]


@dataclass
class RewardBreakdown:
    """Itemised mission rewards."""

    xp: int = 0
    credits: int = 0
    lines: list[tuple[str, int, int]] = field(default_factory=list)

    def add(self, label: str, xp: int, credits: int) -> None:
        """Add a reward line."""
        self.xp += xp
        self.credits += credits
        self.lines.append((label, xp, credits))


def compute_rewards(
    mission: Any,
    optional_done: list[str],
    ghost: bool,
    speed: bool,
    bonus_credits: int,
    progression: dict[str, Any],
    reward_mult: float,
    replay: bool,
) -> RewardBreakdown:
    """Compute the reward breakdown for a successful mission run."""
    mult = reward_mult * (progression["replay_reward_mult"] if replay else 1.0)
    out = RewardBreakdown()
    out.add("Primary objectives", int(mission.reward_xp * mult), int(mission.reward_credits * mult))
    for opt in mission.optional:
        if opt["id"] in optional_done:
            out.add(f"Optional: {opt['text']}", int(opt["xp"] * mult), int(opt["credits"] * mult))
    if ghost:
        out.add("GHOST MODE (zero detection)", int(progression["ghost_bonus_xp"] * mult),
                int(progression["ghost_bonus_credits"] * mult))
    if speed:
        out.add("SPEED DEMON (beat par)", int(progression["speed_bonus_xp"] * mult),
                int(progression["speed_bonus_credits"] * mult))
    if bonus_credits:
        out.add("Recovered backups / bonus files", 0, bonus_credits)
    return out
