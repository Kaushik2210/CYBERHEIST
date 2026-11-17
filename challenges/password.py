"""Password puzzle: deduce a fictional passphrase from pattern clues and per-position feedback."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from core.rng import GameRNG

WORDLIST = [
    "ORBIT", "PIXEL", "VAPOR", "RADAR", "LASER", "SONAR", "NEXUS", "GLYPH",
    "QUARK", "TIGER", "OCEAN", "LUNAR", "CEDAR", "EMBER", "FLINT", "PRISM",
    "RAVEN", "STORM", "MAPLE", "DELTA",
]
SYMBOLS = "!@#$%&*?"


def feedback(secret: str, guess: str) -> str:
    """Per-position marks: '+' right char/right place, '~' in password elsewhere, '.' absent."""
    marks = ["."] * len(secret)
    left = Counter(s for s, g in zip(secret, guess) if s != g)
    for i, (s, g) in enumerate(zip(secret, guess)):
        if s == g:
            marks[i] = "+"
        elif left[g] > 0:
            marks[i] = "~"
            left[g] -= 1
    return "".join(marks)


@dataclass
class PasswordPuzzle:
    """A passphrase built as [symbol] WORD DIGITS [symbol], per ``mask``."""

    secret: str
    mask: str
    words: list[str]
    symbols: str
    digit_ranges: list[tuple[int, int]]
    attempts: int
    history: list[tuple[str, str]] = field(default_factory=list)
    revealed: dict[int, str] = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        """Attempts left."""
        return self.attempts - len(self.history)

    @property
    def solved(self) -> bool:
        """True once the last guess was exact."""
        return bool(self.history) and self.history[-1][0] == self.secret

    def clues(self) -> list[str]:
        """Human-readable clue lines."""
        lines = [f"Pattern: {self.mask}   (W = letter, D = digit, S = symbol)",
                 "Base word is one of: " + " ".join(self.words),
                 f"Symbol is one of: {' '.join(self.symbols)}"]
        for n, (lo, hi) in enumerate(self.digit_ranges, 1):
            lines.append(f"Digit {n} is between {lo} and {hi}.")
        return lines

    def validate(self, text: str) -> str | None:
        """Return an error message if ``text`` does not fit the pattern, else None."""
        text = text.strip().upper()
        if len(text) != len(self.mask):
            return f"Password is {len(self.mask)} characters long."
        for ch, m in zip(text, self.mask):
            if m == "W" and not ch.isalpha():
                return "Letters go where the pattern shows W."
            if m == "D" and not ch.isdigit():
                return "Digits go where the pattern shows D."
            if m == "S" and ch not in self.symbols:
                return f"The symbol must be one of {self.symbols}."
        return None

    def guess(self, text: str) -> str:
        """Submit a validated guess; records and returns the feedback marks."""
        text = text.strip().upper()
        marks = feedback(self.secret, text)
        self.history.append((text, marks))
        return marks

    def reveal_position(self) -> tuple[int, str] | None:
        """Quantum Decoder: reveal one unknown character."""
        known = {i for g, m in self.history for i, c in enumerate(m) if c == "+"} | set(self.revealed)
        for i, ch in enumerate(self.secret):
            if i not in known:
                self.revealed[i] = ch
                return i, ch
        return None

    def add_attempt(self) -> None:
        """Emergency Override."""
        self.attempts += 1

    def next_solver_guess(self) -> str:
        """Autopilot guess consistent with clues and every '+'/non-'+' result so far."""
        return _solver_guess(self.mask, self.words, self.symbols, self.digit_ranges, self.history, self.revealed)


def _solver_guess(mask: str, words: list[str], symbols: str, ranges: list[tuple[int, int]],
                  history: list[tuple[str, str]], revealed: dict[int, str]) -> str:
    wpos = [i for i, m in enumerate(mask) if m == "W"]
    dpos = [i for i, m in enumerate(mask) if m == "D"]
    spos = [i for i, m in enumerate(mask) if m == "S"]

    def fits(i: int, ch: str) -> bool:
        if i in revealed and revealed[i] != ch:
            return False
        for g, marks in history:
            if (marks[i] == "+") != (g[i] == ch):
                return False
        return True

    word = next(w for w in words if all(fits(i, w[k]) for k, i in enumerate(wpos)))
    out = [""] * len(mask)
    for k, i in enumerate(wpos):
        out[i] = word[k]
    for n, i in enumerate(dpos):
        lo, hi = ranges[n]
        out[i] = next(str(d) for d in range(lo, hi + 1) if fits(i, str(d)))
    for i in spos:
        out[i] = next(s for s in symbols if fits(i, s))
    return "".join(out)


def generate(rng: GameRNG, word_count: int = 8, digits: int = 2, symbol_count: int = 4,
             range_width: int = 3, attempts: int = 6) -> PasswordPuzzle:
    """Create a puzzle; attempts are raised to what the solver needs, so it is always solvable."""
    words = rng.sample(WORDLIST, max(4, min(len(WORDLIST), word_count)))
    word = rng.choice(words)
    symbols = "".join(rng.sample(SYMBOLS, max(2, min(len(SYMBOLS), symbol_count))))
    sym = rng.choice(symbols)
    digit_vals = [rng.randint(0, 9) for _ in range(max(1, min(3, digits)))]
    ranges = []
    for d in digit_vals:
        lo = max(0, min(d - rng.randint(0, range_width), 9 - range_width))
        ranges.append((lo, min(9, lo + range_width)))
    prefix = rng.chance(0.5)
    dstr = "".join(map(str, digit_vals))
    secret = f"{sym}{word}{dstr}" if prefix else f"{word}{dstr}{sym}"
    mask = ("S" if prefix else "") + "W" * len(word) + "D" * len(dstr) + ("" if prefix else "S")
    puzzle = PasswordPuzzle(secret, mask, words, symbols, ranges, attempts)
    history: list[tuple[str, str]] = []
    while True:
        g = _solver_guess(mask, words, symbols, ranges, history, {})
        history.append((g, feedback(secret, g)))
        if g == secret:
            break
    puzzle.attempts = max(attempts, len(history))
    return puzzle
