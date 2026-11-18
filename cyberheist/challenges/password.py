"""Password puzzle: deduce a fictional passphrase from pattern clues and per-position feedback."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import product
from typing import Callable

from cyberheist.core.rng import GameRNG

WORDLIST = [
    "ORBIT", "PIXEL", "VAPOR", "RADAR", "LASER", "SONAR", "NEXUS", "GLYPH",
    "QUARK", "TIGER", "OCEAN", "LUNAR", "CEDAR", "EMBER", "FLINT", "PRISM",
    "RAVEN", "STORM", "MAPLE", "DELTA",
]
SYMBOLS = "!@#$%&*?"
VOWELS = set("AEIOU")


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


def word_clue_pool(word: str, rng: GameRNG) -> list[tuple[str, Callable[[str], bool]]]:
    """True statements about ``word`` that can narrow the hidden word list."""
    pool: list[tuple[str, Callable[[str], bool]]] = []
    for c in sorted(set(word)):
        pool.append((f"Contains the letter {c}.", lambda w, c=c: c in w))
    for c in rng.sample([x for x in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if x not in word], 6):
        pool.append((f"Does not contain {c}.", lambda w, c=c: c not in w))
    pool.append((f"Ends with {word[-1]}.", lambda w, c=word[-1]: w[-1] == c))
    starts_vowel = word[0] in VOWELS
    pool.append((f"Starts with a {'vowel' if starts_vowel else 'consonant'}.",
                 lambda w, v=starts_vowel: (w[0] in VOWELS) == v))
    repeats = len(set(word)) < len(word)
    pool.append(("Has a repeated letter." if repeats else "No letter appears twice.",
                 lambda w, r=repeats: (len(set(w)) < len(w)) == r))
    vowels = sum(ch in VOWELS for ch in word)
    pool.append((f"Has exactly {vowels} vowel{'s' if vowels != 1 else ''}.",
                 lambda w, n=vowels: sum(ch in VOWELS for ch in w) == n))
    rng.shuffle(pool)
    return pool


def matches_clue(word: str, clue: str) -> bool:
    """Check ``word`` against one clue as the player reads it."""
    if clue.startswith("Contains the letter "):
        return clue[-2] in word
    if clue.startswith("Does not contain "):
        return clue[-2] not in word
    if clue.startswith("Ends with "):
        return word[-1] == clue[-2]
    if clue.startswith("Starts with a "):
        return (word[0] in VOWELS) == ("vowel" in clue)
    if clue == "Has a repeated letter.":
        return len(set(word)) < len(word)
    if clue == "No letter appears twice.":
        return len(set(word)) == len(word)
    if clue.startswith("Has exactly "):
        return sum(ch in VOWELS for ch in word) == int(clue.split()[2])
    raise ValueError(f"unknown clue: {clue}")


@dataclass
class PasswordPuzzle:
    """A passphrase built as [symbol] WORD DIGITS [symbol], per ``mask``."""

    secret: str
    mask: str
    words: list[str]
    symbols: str
    digit_ranges: list[tuple[int, int]]
    attempts: int
    hide_words: bool = False
    word_clues: list[str] = field(default_factory=list)
    digit_sum: int | None = None
    par: int = 0
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
        lines = [f"Pattern: {self.mask}   (W = letter, D = digit, S = symbol)"]
        if self.hide_words:
            lines.append(f"Base word: {self.mask.count('W')} letters, list not recovered. Known:")
            lines += [f"  - {c}" for c in self.word_clues]
        else:
            lines.append("Base word is one of: " + " ".join(self.words))
        lines.append(f"Symbol is one of: {' '.join(self.symbols)}")
        for n, (lo, hi) in enumerate(self.digit_ranges, 1):
            lines.append(f"Digit {n} is between {lo} and {hi}.")
        if self.digit_sum is not None:
            lines.append(f"The digits add up to {self.digit_sum}.")
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
        """Autopilot guess consistent with the clues and every '+'/non-'+' result so far."""
        return _solver_guess(self.mask, self.words, self.symbols, self.digit_ranges, self.history,
                             self.revealed, self.digit_sum)


def _solver_guess(mask: str, words: list[str], symbols: str, ranges: list[tuple[int, int]],
                  history: list[tuple[str, str]], revealed: dict[int, str], digit_sum: int | None = None) -> str:
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
    options = [[str(d) for d in range(lo, hi + 1) if fits(i, str(d))] for i, (lo, hi) in zip(dpos, ranges)]
    combo = next(c for c in product(*options) if digit_sum is None or sum(map(int, c)) == digit_sum)
    for i, d in zip(dpos, combo):
        out[i] = d
    for i in spos:
        out[i] = next(s for s in symbols if fits(i, s))
    return "".join(out)


def generate(rng: GameRNG, word_count: int = 8, digits: int = 2, symbol_count: int = 4,
             range_width: int = 3, attempts: int = 6, hide_words: bool = False,
             sum_clue: bool = False, margin: int | None = None) -> PasswordPuzzle:
    """Create a puzzle that is always solvable.

    The solver plays it first and its guess count becomes ``par``. With ``margin=None``
    attempts are ``max(attempts, par)``; otherwise exactly ``par + margin``.
    With ``hide_words`` the word list is replaced by letter clues that narrow the full
    dictionary to a few candidates.
    """
    range_width = max(1, min(9, range_width))
    if hide_words:
        word = rng.choice(WORDLIST)
        pool, word_clues = list(WORDLIST), []
        for text, test in word_clue_pool(word, rng):
            narrowed = [w for w in pool if test(w)]
            if len(narrowed) < 2:
                continue                      # would give the word away outright
            if len(narrowed) < len(pool) or len(word_clues) < 2:
                pool, word_clues = narrowed, word_clues + [text]
            if (len(pool) <= 3 and len(word_clues) >= 2) or len(word_clues) >= 5:
                break
        words = pool
    else:
        words = rng.sample(WORDLIST, max(4, min(len(WORDLIST), word_count)))
        word, word_clues = rng.choice(words), []
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
    dsum = sum(digit_vals) if sum_clue else None
    history: list[tuple[str, str]] = []
    while True:
        g = _solver_guess(mask, words, symbols, ranges, history, {}, dsum)
        history.append((g, feedback(secret, g)))
        if g == secret:
            break
    par = len(history)
    total = max(attempts, par) if margin is None else par + max(0, margin)
    return PasswordPuzzle(secret, mask, words, symbols, ranges, total, hide_words, word_clues, dsum, par)
