"""Numbered menus that accept '1', '01', 'b' (back) and '?' (help)."""
from __future__ import annotations

from typing import Sequence

from interface.ui import UI


class Menu:
    """A numbered list of (key, label) options."""

    def __init__(self, title: str, options: Sequence[tuple[str, str]], help_text: str = "",
                 allow_back: bool = True) -> None:
        """Create a menu. ``options`` are (key, label) pairs shown as 01, 02, ..."""
        self.title = title
        self.options = list(options)
        self.help_text = help_text or "Type an option number. 'b' goes back."
        self.allow_back = allow_back

    def render(self, ui: UI) -> None:
        """Draw the menu box."""
        lines = [f"{ui.paint(f'{i:02d}', 'accent')}  {label}" for i, (_, label) in enumerate(self.options, 1)]
        if self.allow_back:
            lines.append(ui.paint(" b   back", "muted"))
        ui.box(self.title, lines)

    def resolve(self, text: str) -> str | None:
        """Map typed text to an option key, or None if it doesn't match."""
        text = text.strip()
        if text.isdigit():
            i = int(text) - 1
            return self.options[i][0] if 0 <= i < len(self.options) else None
        for key, label in self.options:
            if text.lower() in (key.lower(), label.lower()):
                return key
        return None

    def choose(self, ui: UI) -> str | None:
        """Show the menu until a valid choice. Returns the key, or None for back."""
        self.render(ui)
        while True:
            raw = ui.prompt(self.title.lower()).strip()
            if raw.lower() in ("?", "help"):
                ui.info(self.help_text)
                continue
            if self.allow_back and raw.lower() in ("b", "back"):
                return None
            key = self.resolve(raw)
            if key is not None:
                return key
            ui.warn(f"Pick 1-{len(self.options)}" + (", or 'b' to go back." if self.allow_back else "."))
