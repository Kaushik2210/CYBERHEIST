"""Terminal IO abstraction and drawing helpers (boxes, tables, bars, typewriter)."""
from __future__ import annotations

import re
import sys
import time
from collections import deque
from typing import Callable, Iterable, Sequence

from core.state import ScriptExhausted
from interface.theme import Theme

ANSI_RE = re.compile(r"\033\[[0-9;]*m")
AutoFn = Callable[[], str] | None


def visible_len(text: str) -> int:
    """Length of ``text`` ignoring ANSI escape codes."""
    return len(ANSI_RE.sub("", text))


class ConsoleIO:
    """Real terminal IO."""

    autopilot = False

    def write(self, text: str = "", end: str = "\n") -> None:
        """Print text."""
        try:
            sys.stdout.write(text + end)
        except UnicodeEncodeError:
            sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + end)
        sys.stdout.flush()

    def read(self, prompt: str, auto: AutoFn = None) -> str:
        """Read a line. Raises EOFError when input ends; the game saves and quits on it."""
        return input(prompt).lstrip("﻿")

    def sleep(self, seconds: float) -> None:
        """Pause for animations."""
        if seconds > 0:
            time.sleep(seconds)

    def bell(self) -> None:
        """Ring the terminal bell."""
        sys.stdout.write("\a")
        sys.stdout.flush()

    def clear(self) -> None:
        """Clear the screen (ANSI on a real terminal, blank lines when piped)."""
        if sys.stdout.isatty():
            sys.stdout.write("\033[2J\033[H")
        else:
            sys.stdout.write("\n" * 40)
        sys.stdout.flush()


class ScriptedIO:
    """Test IO: feeds scripted inputs and records output.

    With ``autopilot=True``, prompts that supply an ``auto`` answer function are
    answered by it (used by the scripted mission solver); other prompts consume
    the scripted queue.
    """

    def __init__(self, inputs: Iterable[str] = (), autopilot: bool = False) -> None:
        """Create a scripted IO with a queue of inputs."""
        self.queue: deque[str] = deque(inputs)
        self.autopilot = autopilot
        self.output: list[str] = []
        self.bells = 0

    def write(self, text: str = "", end: str = "\n") -> None:
        """Record output (ANSI stripped)."""
        self.output.append(ANSI_RE.sub("", text))

    def read(self, prompt: str, auto: AutoFn = None) -> str:
        """Return the autopilot answer or the next scripted input."""
        self.output.append(ANSI_RE.sub("", prompt))
        if self.autopilot and auto is not None:
            answer = auto()
        elif self.queue:
            answer = self.queue.popleft()
        else:
            raise ScriptExhausted(f"no scripted input left for prompt {prompt!r}")
        self.output.append(f"<{answer}>")
        return answer

    def sleep(self, seconds: float) -> None:
        """No-op in tests."""

    def bell(self) -> None:
        """Count bells instead of ringing."""
        self.bells += 1

    def clear(self) -> None:
        """Record that the screen was cleared."""
        self.output.append("<screen cleared>")

    def text(self) -> str:
        """All recorded output as one string."""
        return "\n".join(self.output)


class UI:
    """Drawing helpers bound to an IO and a theme."""

    WIDTH = 78

    def __init__(self, io: ConsoleIO | ScriptedIO, theme: Theme, typewriter: bool = True,
                 speed: float = 1.0, animations: bool = True, sound: bool = False) -> None:
        """Create the UI facade."""
        self.io = io
        self.theme = theme
        self.typewriter_on = typewriter
        self.speed = speed
        self.animations = animations
        self.sound = sound

    # -- basic output ------------------------------------------------------
    def say(self, text: str = "", role: str | None = None) -> None:
        """Print a line, optionally coloured."""
        self.io.write(self.theme.paint(text, role) if role else text)

    def blank(self) -> None:
        """Print an empty line."""
        self.io.write("")

    def paint(self, text: str, role: str = "primary") -> str:
        """Colour a string with the theme."""
        return self.theme.paint(text, role)

    def ok(self, text: str) -> None:
        """Success line."""
        self.say(f"[+] {text}", "ok")

    def warn(self, text: str) -> None:
        """Warning line."""
        self.say(f"[!] {text}", "warn")

    def error(self, text: str) -> None:
        """Error line."""
        self.say(f"[x] {text}", "danger")

    def info(self, text: str) -> None:
        """Info line."""
        self.say(f"[i] {text}", "info")

    def clear_screen(self) -> None:
        """Wipe the screen, e.g. to hide something the player had to memorise."""
        clear = getattr(self.io, "clear", None)
        if callable(clear):
            clear()
        else:
            for _ in range(40):
                self.io.write("")

    def alert(self) -> None:
        """Ring the bell when sound is enabled."""
        if self.sound:
            self.io.bell()

    def pause(self, seconds: float) -> None:
        """Sleep scaled by animation speed, only when animations are on."""
        if self.animations:
            self.io.sleep(seconds / max(0.25, self.speed))

    def typewriter(self, text: str, role: str = "primary", delay: float = 0.008) -> None:
        """Print text one character at a time (instant when disabled)."""
        if not (self.typewriter_on and self.animations) or isinstance(self.io, ScriptedIO):
            self.say(text, role)
            return
        code = self.theme.code(role)
        self.io.write(code, end="")
        for ch in text:
            self.io.write(ch, end="")
            self.io.sleep(delay / max(0.25, self.speed))
        self.io.write(self.theme.paint("", role) if code else "")

    # -- input ---------------------------------------------------------------
    def prompt(self, label: str = "", auto: AutoFn = None) -> str:
        """Ask for a line of input with the themed prompt."""
        raw = self.io.read(self.theme.paint(f"{label}> ", "primary"), auto)
        return (raw or "").strip()

    def confirm(self, question: str, auto: AutoFn = None) -> bool:
        """Yes/no question; only 'y'/'yes' counts as yes."""
        return self.prompt(f"{question} [y/N] ", auto).lower() in ("y", "yes")

    def wait(self, label: str = "Press ENTER to continue", auto: AutoFn = None) -> str:
        """Wait for ENTER; returns what was typed."""
        return self.prompt(self.theme.paint(label, "muted"), auto or (lambda: ""))

    # -- widgets -------------------------------------------------------------
    def box(self, title: str, lines: Sequence[str], role: str = "primary", width: int | None = None) -> None:
        """Draw a titled box around ``lines``."""
        g = self.theme.glyphs
        width = width or self.WIDTH
        inner = width - 4
        top_title = f" {title} " if title else ""
        top = g["tl"] + g["h"] + top_title + g["h"] * max(0, width - 3 - len(top_title)) + g["tr"]
        self.say(top, role)
        for line in lines:
            for chunk in wrap(line, inner):
                pad = inner - visible_len(chunk)
                self.io.write(self.paint(g["v"], role) + " " + chunk + " " * max(0, pad) + " " + self.paint(g["v"], role))
        self.say(g["bl"] + g["h"] * (width - 2) + g["br"], role)

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
        """Draw a simple aligned table."""
        cells = [[str(c) for c in r] for r in rows]
        widths = [len(h) for h in headers]
        for r in cells:
            for i, c in enumerate(r):
                widths[i] = max(widths[i], visible_len(c))
        head = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        self.say(head, "accent")
        self.say("  ".join("-" * w for w in widths), "dim")
        for r in cells:
            self.io.write("  ".join(c + " " * (widths[i] - visible_len(c)) for i, c in enumerate(r)))

    def bar(self, value: float, maximum: float, width: int = 30, role: str = "primary") -> str:
        """Return a coloured progress bar string."""
        g = self.theme.glyphs
        frac = 0.0 if maximum <= 0 else max(0.0, min(1.0, value / maximum))
        filled = int(round(frac * width))
        return self.paint(g["full"] * filled, role) + self.paint(g["empty"] * (width - filled), "muted")

    def rule(self, role: str = "dim") -> None:
        """Horizontal rule."""
        self.say(self.theme.glyphs["h"] * self.WIDTH, role)


def wrap(text: str, width: int) -> list[str]:
    """Word-wrap a line to ``width`` visible characters (ANSI-aware enough for our use)."""
    if visible_len(text) <= width:
        return [text]
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if visible_len(cur) + visible_len(w) + (1 if cur else 0) > width:
            if cur:
                lines.append(cur)
            while visible_len(w) > width:
                lines.append(w[:width])
                w = w[width:]
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines or [""]
