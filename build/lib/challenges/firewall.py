"""Firewall puzzle: a Mastermind-style ordered sequence of fictional rule tokens."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import permutations, product
from typing import Iterator

from core.rng import GameRNG

RULE_POOL = [
    "ALLOW_SSH_DECOY", "DENY_RELAY", "DROP_ICMP_ECHO", "PASS_NTP_SYNC",
    "BLOCK_TELNET_X", "ROUTE_VPN_SHADOW", "LOG_DNS_TRACE", "FLUSH_ARP_CACHE",
]


def score(secret: tuple[int, ...], guess: tuple[int, ...]) -> tuple[int, int]:
    """Return (exact, partial): right token in right slot, right token in wrong slot.

    Counts are multiset-aware, so chains with repeated rules score correctly.
    """
    exact = sum(s == g for s, g in zip(secret, guess))
    common = sum((Counter(secret) & Counter(guess)).values())
    return exact, common - exact


def candidates(pool_size: int, length: int, repeats: bool) -> Iterator[tuple[int, ...]]:
    """Every possible chain, in a fixed order."""
    if repeats:
        return product(range(pool_size), repeat=length)
    return permutations(range(pool_size), length)


def solve(secret: tuple[int, ...], pool_size: int, length: int, repeats: bool = False) -> list[tuple[int, ...]]:
    """Play with a first-consistent-candidate strategy; return the guesses made."""
    pool = list(candidates(pool_size, length, repeats))
    guesses: list[tuple[int, ...]] = []
    while True:
        guess = pool[0]
        guesses.append(guess)
        fb = score(secret, guess)
        if fb[0] == length:
            return guesses
        pool = [c for c in pool if score(c, guess) == fb]


@dataclass
class FirewallPuzzle:
    """One firewall lock. Tokens are indices into ``pool``."""

    pool: list[str]
    secret: tuple[int, ...]
    attempts: int
    repeats: bool = False
    par: int = 0
    history: list[tuple[tuple[int, ...], tuple[int, int]]] = field(default_factory=list)
    revealed: dict[int, int] = field(default_factory=dict)

    @property
    def length(self) -> int:
        """Number of slots in the rule chain."""
        return len(self.secret)

    @property
    def remaining(self) -> int:
        """Attempts left."""
        return self.attempts - len(self.history)

    @property
    def solved(self) -> bool:
        """True once a guess matched every slot."""
        return bool(self.history) and self.history[-1][1][0] == self.length

    def parse(self, text: str) -> tuple[int, ...] | str:
        """Parse '1 4 2 7' (1-based) into a guess, or return an error message."""
        parts = text.replace(",", " ").split()
        if len(parts) != self.length:
            return f"Enter exactly {self.length} rule numbers, e.g. {' '.join(str(i + 1) for i in range(self.length))}."
        try:
            idx = tuple(int(p) - 1 for p in parts)
        except ValueError:
            return "Rule numbers only, separated by spaces."
        if any(not 0 <= i < len(self.pool) for i in idx):
            return f"Rule numbers run from 1 to {len(self.pool)}."
        if not self.repeats and len(set(idx)) != len(idx):
            return "Each rule can appear only once in the chain."
        return idx

    def guess(self, idx: tuple[int, ...]) -> tuple[int, int]:
        """Submit a parsed guess; records and returns (exact, partial)."""
        fb = score(self.secret, idx)
        self.history.append((idx, fb))
        return fb

    def reveal_slot(self) -> tuple[int, int] | None:
        """Reveal one unrevealed slot (Quantum Decoder). Returns (slot, token) or None."""
        for slot, tok in enumerate(self.secret):
            if slot not in self.revealed:
                self.revealed[slot] = tok
                return slot, tok
        return None

    def add_attempt(self) -> None:
        """Grant one extra attempt (Emergency Override)."""
        self.attempts += 1

    def next_solver_guess(self) -> str:
        """Answer the autopilot would type next (consistent with all feedback so far)."""
        for cand in candidates(len(self.pool), self.length, self.repeats):
            if all(score(cand, g) == fb for g, fb in self.history):
                return " ".join(str(i + 1) for i in cand)
        return " ".join(str(i + 1) for i in self.secret)


def generate(rng: GameRNG, pool_size: int, length: int, attempts: int,
             repeats: bool = False, margin: int | None = None) -> FirewallPuzzle:
    """Create a puzzle that is always solvable.

    The built-in solver plays it first; its guess count becomes the puzzle's ``par``.
    With ``margin=None`` attempts are ``max(attempts, par)``; with a margin they are
    exactly ``par + margin``, which is how Normal and Hard keep the lock tight.
    """
    pool_size = max(6, min(len(RULE_POOL), pool_size))
    length = max(3, min(pool_size - (0 if repeats else 1), length))
    pool = rng.sample(RULE_POOL, pool_size)
    if repeats:
        secret = tuple(rng.randint(0, pool_size - 1) for _ in range(length))
    else:
        secret = tuple(rng.sample(range(pool_size), length))
    par = len(solve(secret, pool_size, length, repeats))
    total = max(attempts, par) if margin is None else par + max(0, margin)
    return FirewallPuzzle(pool=pool, secret=secret, attempts=total, repeats=repeats, par=par)
