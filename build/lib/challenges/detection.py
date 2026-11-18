"""The shared detection meter (0-100) used by every challenge."""
from __future__ import annotations

from typing import Any


class DetectionMeter:
    """Tracks how close the player is to being caught.

    Gains are scaled by difficulty and by the Ghost Proxy. A Signal Mask
    absorbs one alarm per mission. At the fail threshold the mission fails.
    """

    def __init__(self, cfg: dict[str, Any], difficulty_mult: float = 1.0,
                 ghost_proxy: bool = False, signal_mask: bool = False) -> None:
        """Build a meter from the ``detection`` block of settings.json."""
        self.cfg = cfg
        self.thresholds = cfg["thresholds"]
        self.mult = difficulty_mult * (cfg["ghost_proxy_mult"] if ghost_proxy else 1.0)
        self.mask_charges = 1 if signal_mask else 0
        self.level = 0.0
        self.peak = 0.0

    def add(self, amount: float) -> float:
        """Add detection (scaled by modifiers). Returns the amount actually added."""
        if amount <= 0:
            return 0.0
        gained = amount * self.mult
        self.level = min(float(self.thresholds["fail"]), self.level + gained)
        self.peak = max(self.peak, self.level)
        return gained

    def reduce(self, amount: float) -> None:
        """Lower detection (never below zero)."""
        self.level = max(0.0, self.level - amount)

    def wrong_guess(self) -> float:
        """Apply the penalty for one wrong guess."""
        return self.add(self.cfg["wrong_guess"])

    def overtime(self, ticks_over: float) -> float:
        """Apply the penalty for ticks spent past the grace period."""
        return self.add(self.cfg["overtime_per_tick"] * ticks_over)

    def alarm(self) -> tuple[float, bool]:
        """Trigger an alarm. Returns (amount added, absorbed by Signal Mask)."""
        if self.mask_charges > 0:
            self.mask_charges -= 1
            return 0.0, True
        return self.add(self.cfg["alarm"]), False

    @property
    def failed(self) -> bool:
        """True once the meter reaches the fail threshold."""
        return self.level >= self.thresholds["fail"]

    @property
    def status(self) -> str:
        """CLEAR / ELEVATED / HIGH / CRITICAL / DETECTED."""
        t = self.thresholds
        if self.level >= t["fail"]:
            return "DETECTED"
        if self.level >= t["critical"]:
            return "CRITICAL"
        if self.level >= t["high"]:
            return "HIGH"
        if self.level >= t["elevated"]:
            return "ELEVATED"
        return "CLEAR"

    @property
    def role(self) -> str:
        """Theme colour role for the current status."""
        return {"CLEAR": "ok", "ELEVATED": "warn", "HIGH": "danger"}.get(self.status, "critical")
