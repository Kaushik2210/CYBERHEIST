"""Encryption lab: classic ciphers and encodings that hide a plaintext clue."""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field

from cyberheist.core.rng import GameRNG

A = string.ascii_uppercase
KINDS = ("caesar", "vigenere", "substitution", "binary", "hex", "pattern", "layered")

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


# The game's "language": a text reads as plaintext when every word is one of these.
VOCAB = {w for p in PHRASES for w in p.split()}


def caesar_candidates(text: str) -> list[tuple[int, str]]:
    """Every shift that turns ``text`` into words from the game vocabulary."""
    out = []
    for s in range(1, 26):
        plain = caesar(text, -s)
        if all(w in VOCAB for w in plain.split()):
            out.append((s, plain))
    return out


def key_from_crib(ciphertext: str, crib: str, key_len: int) -> str:
    """Recover a Vigenère key from known plaintext at the start of the message."""
    letters = [c for c in ciphertext if c in A]
    return "".join(A[(A.index(letters[i]) - A.index(crib[i])) % 26] for i in range(key_len))


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
    crib: str = ""
    key_len: int = 0
    tough: bool = False
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

    def tool(self, arg: str, verb: str | None = None) -> str:
        """Lab helpers: 'shift N' (Caesar, layered), 'apply KEY' (Vigenère), 'unhex' (layered)."""
        verb = verb or {"caesar": "shift", "vigenere": "apply"}.get(self.kind, "")
        if self.kind == "layered" and verb == "unhex":
            return f"Hex layer removed: {from_hex(self.ciphertext)}"
        if self.kind in ("caesar", "layered") and verb == "shift":
            try:
                n = int(arg)
            except ValueError:
                return "Usage: shift <number 1-25>"
            base = self.ciphertext if self.kind == "caesar" else from_hex(self.ciphertext)
            return f"Shift -{n}: {caesar(base, -n)}"
        if self.kind == "vigenere" and verb == "apply":
            if not arg.isalpha():
                return "Usage: apply <keyword>"
            return f"Key {arg.upper()}: {vigenere(self.ciphertext, arg, decrypt=True)}"
        return "No lab tool for that here. Try 'hint'."

    def add_attempt(self) -> None:
        """Emergency Override: one extra attempt."""
        self.attempts += 1

    def solver_answer(self) -> str:
        """What the autopilot types, worked out only from what the player is shown."""
        if self.kind == "caesar":
            return caesar_candidates(self.ciphertext)[0][1]
        if self.kind == "layered":
            return caesar_candidates(from_hex(self.ciphertext))[0][1]
        if self.kind == "vigenere":
            key = self.key if not self.tough else key_from_crib(self.ciphertext, self.crib, self.key_len)
            return vigenere(self.ciphertext, key, decrypt=True)
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
    step = xs[1] - xs[0]
    if xs[1] and xs[2] % xs[1] == 0:
        m = xs[2] // xs[1]
        if all(xs[i] == (xs[i - 1] + step if i % 2 == 1 else xs[i - 1] * m) for i in range(1, len(xs))):
            return xs[-1] + step if len(xs) % 2 == 1 else xs[-1] * m
    # Polynomial (squares, cubes): extend the difference table until a row is constant.
    rows = [xs]
    while len(set(rows[-1])) > 1 and len(rows[-1]) > 1:
        rows.append([b - a for a, b in zip(rows[-1], rows[-1][1:])])
    return sum(r[-1] for r in rows)


def generate(rng: GameRNG, kind: str, attempts: int = 3, tough: bool = False) -> CipherPuzzle:
    """Create a puzzle of ``kind``. Every puzzle is checked solvable before it is returned."""
    if kind not in KINDS:
        raise ValueError(f"unknown cipher kind {kind}")
    phrase = rng.choice(PHRASES)
    if kind in ("caesar", "layered"):
        while True:
            s = rng.randint(1, 25)
            if len(caesar_candidates(caesar(phrase, s))) == 1:
                break
            phrase = rng.choice(PHRASES)
        hints = [f"The shift is {'even' if s % 2 == 0 else 'odd'}.",
                 f"The shift is between {max(1, s - 3)} and {min(25, s + 3)}."]
        if not tough:
            hints.append(f"The shift is {s}.")
        if kind == "caesar":
            brief = "Caesar shift. Try 'shift <n>' in the lab." + (" Each trial is logged." if tough else "")
            p = CipherPuzzle(kind, caesar(phrase, s), phrase, brief, hints, attempts, shift=s, tough=tough)
        else:
            p = CipherPuzzle(kind, to_hex(caesar(phrase, s)), phrase,
                             "Two layers: hex-encoded ASCII over a Caesar shift. 'unhex' peels the outer "
                             "layer, then 'shift <n>' works on what's underneath.",
                             ["The outer layer is hex: 41 = 'A', 20 = space."] + hints, attempts,
                             shift=s, tough=tough)
    elif kind == "vigenere":
        first = phrase.split()[0]
        key = rng.choice([k for k in KEYWORDS if len(k) <= len(first)] if tough else KEYWORDS)
        if tough:
            p = CipherPuzzle(kind, vigenere(phrase, key), phrase,
                             f"Vigenère cipher, key unknown. The message starts with {first}. "
                             f"Key length: {len(key)}. Work out the key, then 'apply <key>'.",
                             ["Key letter = cipher letter - known plain letter (A=0, wrap at 26).",
                              f"The key starts with {key[0]}."], attempts,
                             key=key, crib=first, key_len=len(key), tough=True)
        else:
            p = CipherPuzzle(kind, vigenere(phrase, key), phrase,
                             f"Vigenère cipher. Intercepted keyword: {key}. Try 'apply <key>'.",
                             ["Subtract the key letter (A=0) from each cipher letter.",
                              f"First word decodes to {first[:2]}..."], attempts, key=key)
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
        word = rng.choice(PHRASES).split()[0] + rng.choice(WORDS) if tough else rng.choice(WORDS)
        enc = to_binary(word) if kind == "binary" else to_hex(word)
        hints = ["'A' is 01000001 in binary, 41 in hex." if kind == "binary" else "'A' is 41 in hex, 'Z' is 5A."]
        if not tough:
            hints.append(f"The word starts with {word[0]}.")
        p = CipherPuzzle(kind, enc, word, f"{kind.title()}-encoded ASCII word.", hints, attempts, tough=tough)
    else:
        rules = ["arith", "geom", "fib", "square"] + (["alt", "cube"] if tough else [])
        rule = rng.choice(rules)
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
        elif rule == "alt":
            d, m = rng.randint(2, 9), rng.randint(2, 3)
            xs = [a]
            while len(xs) < 6:
                xs.append(xs[-1] + d if len(xs) % 2 == 1 else xs[-1] * m)
        elif rule == "cube":
            xs = [(a + i) ** 3 for i in range(6)]
        else:
            xs = [(a + i) ** 2 for i in range(6)]
        seq = ", ".join(str(x) for x in xs[:5])
        names = {"arith": "add a constant", "geom": "multiply by a constant", "fib": "add the two previous terms",
                 "square": "consecutive squares", "alt": "alternate adding and multiplying",
                 "cube": "consecutive cubes"}
        hints = ["Look at the differences between terms."] + ([] if tough else [f"The rule is {names[rule]}."])
        p = CipherPuzzle(kind, seq, str(xs[5]), "Pattern lock: enter the next number in the sequence.",
                         hints, attempts, tough=tough)
    if normalize(p.solver_answer()) != normalize(p.answer):
        raise AssertionError(f"generated unsolvable {kind} puzzle")
    return p
