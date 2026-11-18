"""Colour themes, ANSI handling and box-drawing glyph sets."""
from __future__ import annotations

import os
import sys

RESET = "\033[0m"

_PALETTES: dict[str, dict[str, str]] = {
    "green": {"primary": "\033[92m", "dim": "\033[32m", "accent": "\033[97m"},
    "amber": {"primary": "\033[93m", "dim": "\033[33m", "accent": "\033[97m"},
    "cyan":  {"primary": "\033[96m", "dim": "\033[36m", "accent": "\033[97m"},
}
_STATUS = {
    "ok": "\033[92m", "warn": "\033[93m", "danger": "\033[91m",
    "critical": "\033[95m", "info": "\033[96m", "muted": "\033[90m", "bold": "\033[1m",
}

UNICODE_GLYPHS = {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║",
                  "full": "█", "empty": "░", "arrow": "→", "dot": "●", "hollow": "○"}
ASCII_GLYPHS = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "=", "v": "|",
                "full": "#", "empty": ".", "arrow": "->", "dot": "*", "hollow": "o"}


def enable_ansi() -> None:
    """Enable ANSI escape processing on Windows consoles (no-op elsewhere)."""
    if os.name == "nt":
        os.system("")


def supports_unicode(stream: object = None) -> bool:
    """Return True if the output encoding can print box-drawing characters."""
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "╔═║█░→●".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


class Theme:
    """Resolves semantic colour names to ANSI codes for the active theme."""

    def __init__(self, name: str = "green", color: bool | None = None, unicode: bool | None = None) -> None:
        """Create a theme. Colour is disabled when NO_COLOR is set."""
        self.name = name if name in _PALETTES else "green"
        if color is None:
            color = "NO_COLOR" not in os.environ
        self.color = color
        self.glyphs = UNICODE_GLYPHS if (supports_unicode() if unicode is None else unicode) else ASCII_GLYPHS

    def set_name(self, name: str) -> None:
        """Switch palette."""
        if name in _PALETTES:
            self.name = name

    def code(self, role: str) -> str:
        """Return the ANSI code for a role ('primary', 'danger', ...)."""
        if not self.color:
            return ""
        return _PALETTES[self.name].get(role) or _STATUS.get(role, "")

    def paint(self, text: str, role: str = "primary") -> str:
        """Wrap ``text`` in the colour for ``role``."""
        code = self.code(role)
        return f"{code}{text}{RESET}" if code else text
