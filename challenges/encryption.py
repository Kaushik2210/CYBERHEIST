"""Encryption lab: classic ciphers and encodings that hide a plaintext clue."""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field

from core.rng import GameRNG

A = string.ascii_uppercase
KINDS = ("caesar", "vigenere", "substitution", "binary", "hex", "pattern")

PHRASES = [
    "NEON GHOST", "SILENT ORCHID", "PHANTOM RELAY", "BLACK MIRROR", "CHROME SPARROW",
    "IRON LANTERN", "VELVET STATIC", "GLASS ORACLE", "RUST VIPER", "MIDNIGHT ATLAS",
    "COBALT HARBOR", "ECHO CHAMBER", "AMBER CIRCUIT", "HOLLOW CROWN", "QUIET THUNDER",
    "ZERO MERIDIAN", "PAPER TIGER", "SOLAR WIDOW", "DIGITAL SAINT", "FROZEN SIGNAL",
]
KEYWORDS = ["NOVA", "HELIX", "RAVEN", "PRISM", "ONYX", "VECTOR", "LOTUS", "ZENITH"]
WORDS = ["KEY", "GATE", "NODE", "CODE", "SYNC", "LINK", "VOID", "BYTE", "CORE", "WIRE"]


# -- primitives --------------------------------------------------------------------
def normalize(text: str) -> str:
    """Uppercase, keep letters/digits, collapse whitespace."""
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split())


def caesar(text: str, shift: int) -> str:
    """Shift letters by ``shift`` (negative to decode)."""
    return "".join(A[(A.index(c) + shift) % 26] if c in A else c for c in text.upper())


def vigenere(text: str, key: str, decrypt: bool = False) -> str:
    """Vigenère over letters only; the key advances on letters, not spaces."""
    out, i = [], 0
    for c in text.upper():
        if c in A:
            k = A.index(key[i % len(key)].upper())
            out.append(A[(A.index(c) + (-k if decrypt else k)) % 26])
            i += 1
        else:
            out.append(c)
    return "".join(out)


def substitute(text: str, mapping: dict[str, str]) -> str:
    """Apply a letter mapping."""
    return "".join(mapping.get(c, c) for c in text.upper())


def to_binary(text: str) -> str:
    """Text to space-separated 8-bit groups."""
    return " ".join(f"{ord(c):08b}" for c in text)


def from_binary(bits: str) -> str:
    """Space-separated 8-bit groups back to text."""
    return "".join(chr(int(b, 2)) for b in bits.split())


def to_hex(text: str) -> str:
    """Text to space-separated hex bytes."""
    return " ".join(f"{ord(c):02X}" for c in text)


def from_hex(data: str) -> str:
    """Space-separated hex bytes back to text."""
    return "".join(chr(int(h, 16)) for h in data.split())


def letter_pattern(text: str) -> tuple:
    """Shape of a phrase under any substitution: word lengths and repeat structure."""
    seen: dict[str, int] = {}
    return tuple(seen.setdefault(c, len(seen)) if c in A else -1 for c in text)


# -- puzzle ------------------------------------------------------------------------
@dataclass
class CipherPuzzle:
    """One lab puzzle. The player types the plaintext (or the next number for patterns)."""

    kind: str
    ciphertext: str
    answer: str
    brief: str
    hints: list[str]
    attempts: int = 3
    candidates: list[str] = field(default_factory=list)
    key: str = ""
    shift: int = 0
    hints_used: int = 0
    wrong: int = 0
    solved: bool = False

    @property
    def remaining(self) -> int:
        """Attempts left."""
        return self.attempts - self.wrong

    def check(self, text: str) -> bool:
        """Compare a typed answer to the plaintext; counts a wrong attempt if it misses."""
        if normalize(text) == normalize(self.answer):
            self.solved = True
            return True
        self.wrong += 1
        return False

    def next_hint(self) -> str | None:
        """Reveal the next hint, or None when they are used up."""
        if self.hints_used >= len(self.hints):
            return None
        self.hints_used += 1
        return self.hints[self.hints_used - 1]

    def reveal_detail(self) -> str:
        """Quantum Decoder: reveal the first letters of the answer."""
        n = min(len(self.answer), 3 + self.hints_used)
        return f"Plaintext begins: {self.answer[:n]}..."

    def tool(self, arg: str) -> str:
        """Lab helper: 'shift N' trial for Caesar, 'apply KEY' for Vigenère."""
        if self.kind == "caesar":
            try:
                n = int(arg)
            except ValueError:
                return "Usage: shift <number 1-25>"
            return f"Shift -{n}: {caesar(self.ciphertext, -n)}"
        if self.kind == "vigenere":
            if not arg.isalpha():
                return "Usage: apply <keyword>"
            return f"Key {arg.upper()}: {vigenere(self.ciphertext, arg, decrypt=True)}"
        return "No lab tool for this cipher. Try 'hint'."

    def add_attempt(self) -> None:
        """Emergency Override: one extra attempt."""
        self.attempts += 1

    def solver_answer(self) -> str:
        """What the autopilot types: derived from the puzzle data, not read from the answer field."""
        if self.kind == "caesar":
            return caesar(self.ciphertext, -self.shift)
        if self.kind == "vigenere":
            return vigenere(self.ciphertext, self.key, decrypt=True)
        if self.kind == "substitution":
            shape = letter_pattern(self.ciphertext)
            return next(c for c in self.candidates if letter_pattern(c) == shape)
        if self.kind == "binary":
            return from_binary(self.ciphertext)
        if self.kind == "hex":
            return from_hex(self.ciphertext)
        return str(_next_term(self.ciphertext))


def _next_term(seq_text: str) -> int:
    """Solve a generated sequence by testing the rule families we generate."""
    xs = [int(x) for x in seq_text.replace(",", " ").split()]
    d = [b - a for a, b in zip(xs, xs[1:])]
    if len(set(d)) == 1:
        return xs[-1] + d[0]
    if all(a and b % a == 0 for a, b in zip(xs, xs[1:])) and len({b // a for a, b in zip(xs, xs[1:])}) == 1:
        return xs[-1] * (xs[1] // xs[0])
    if all(xs[i] == xs[i - 1] + xs[i - 2] for i in range(2, len(xs))):
        return xs[-1] + xs[-2]
    dd = [b - a for a, b in zip(d, d[1:])]
    return xs[-1] + d[-1] + dd[0]


def generate(rng: GameRNG, kind: str, attempts: int = 3) -> CipherPuzzle:
    """Create a puzzle of ``kind``. Every puzzle is checked solvable before it is returned."""
    if kind not in KINDS:
        raise ValueError(f"unknown cipher kind {kind}")
    phrase = rng.choice(PHRASES)
    if kind == "caesar":
        s = rng.randint(1, 25)
        p = CipherPuzzle(kind, caesar(phrase, s), phrase, "Caesar shift. Try 'shift <n>' in the lab.",
                         [f"The shift is {'even' if s % 2 == 0 else 'odd'}.",
                          f"The shift is between {max(1, s - 3)} and {min(25, s + 3)}.",
                          f"The shift is {s}."], attempts, shift=s)
    elif kind == "vigenere":
        key = rng.choice(KEYWORDS)
        p = CipherPuzzle(kind, vigenere(phrase, key), phrase,
                         f"Vigenère cipher. Intercepted keyword: {key}. Try 'apply <key>'.",
                         ["Subtract the key letter (A=0) from each cipher letter.",
                          f"First word decodes to {phrase.split()[0][:2]}..."], attempts, key=key)
    elif kind == "substitution":
        letters = list(A)
        rng.shuffle(letters)
        mapping = dict(zip(A, letters))
        shape = letter_pattern(phrase)
        others = [x for x in PHRASES if x != phrase and letter_pattern(x) != shape]
        cands = rng.sample(others, 3) + [phrase]
        rng.shuffle(cands)
        plain_letter = rng.choice([c for c in phrase if c in A])
        p = CipherPuzzle(kind, substitute(phrase, mapping), phrase,
                         "Substitution cipher. Chatter matches one of these phrases:", [
                             f"Cipher {mapping[plain_letter]} = plain {plain_letter}.",
                             "Compare word lengths and repeated letters.",
                         ], attempts, candidates=cands)
        p.brief += " " + " | ".join(cands)
    elif kind in ("binary", "hex"):
        word = rng.choice(WORDS)
        enc = to_binary(word) if kind == "binary" else to_hex(word)
        p = CipherPuzzle(kind, enc, word, f"{kind.title()}-encoded ASCII word.",
                         ["'A' is 01000001 in binary, 41 in hex." if kind == "binary" else "'A' is 41 in hex, 'Z' is 5A.",
                          f"The word starts with {word[0]}."], attempts)
    else:
        rule = rng.choice(["arith", "geom", "fib", "square"])
        a = rng.randint(1, 9)
        if rule == "arith":
            d = rng.randint(2, 12)
            xs = [a + d * i for i in range(6)]
        elif rule == "geom":
            r = rng.randint(2, 3)
            xs = [a * r ** i for i in range(6)]
        elif rule == "fib":
            xs = [a, a + rng.randint(1, 5)]
            while len(xs) < 6:
                xs.append(xs[-1] + xs[-2])
        else:
            xs = [(a + i) ** 2 for i in range(6)]
        seq = ", ".join(str(x) for x in xs[:5])
        p = CipherPuzzle(kind, seq, str(xs[5]), "Pattern lock: enter the next number in the sequence.",
                         ["Look at the differences between terms.",
                          f"The rule is {'add a constant' if rule == 'arith' else 'multiply by a constant' if rule == 'geom' else 'add the two previous terms' if rule == 'fib' else 'consecutive squares'}."],
                         attempts)
    if normalize(p.solver_answer()) != normalize(p.answer):
        raise AssertionError(f"generated unsolvable {kind} puzzle")
    return p
