"""Configuration loading, user settings and shared exceptions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "settings.json"

VALID_THEMES = ("green", "amber", "cyan")
VALID_DIFFICULTIES = ("easy", "normal", "hard")


class MissionFailed(Exception):
    """Raised inside a mission when a failure condition is met."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MissionAborted(Exception):
    """Raised when the player chooses to abort a mission from the pause menu."""


class ScriptExhausted(Exception):
    """Raised by the scripted test IO when it runs out of inputs."""


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load the balance/config file and return it as a dict."""
    target = path or CONFIG_PATH
    with open(target, "r", encoding="utf-8") as fh:
        return json.load(fh)


class Settings:
    """Player-adjustable settings, backed by defaults from ``settings.json``."""

    KEYS = ("difficulty", "theme", "animations", "animation_speed", "typewriter", "sound")

    def __init__(self, defaults: dict[str, Any], overrides: dict[str, Any] | None = None) -> None:
        """Build settings from defaults plus (validated) overrides."""
        self._defaults = copy.deepcopy(defaults)
        self.values: dict[str, Any] = copy.deepcopy(defaults)
        for key, value in (overrides or {}).items():
            self.set(key, value, strict=False)

    def set(self, key: str, value: Any, strict: bool = True) -> bool:
        """Set a value after validation. Returns False (or raises if strict) when invalid."""
        ok = self._valid(key, value)
        if not ok:
            if strict:
                raise ValueError(f"invalid value for {key}: {value!r}")
            return False
        self.values[key] = value
        return True

    @staticmethod
    def _valid(key: str, value: Any) -> bool:
        if key == "difficulty":
            return value in VALID_DIFFICULTIES
        if key == "theme":
            return value in VALID_THEMES
        if key in ("animations", "typewriter", "sound"):
            return isinstance(value, bool)
        if key == "animation_speed":
            return isinstance(value, (int, float)) and 0.25 <= float(value) <= 4.0
        return False

    def get(self, key: str) -> Any:
        """Return a setting value."""
        return self.values[key]

    def reset(self) -> None:
        """Restore every setting to its default."""
        self.values = copy.deepcopy(self._defaults)

    def as_dict(self) -> dict[str, Any]:
        """Return a copy of the current values."""
        return dict(self.values)
