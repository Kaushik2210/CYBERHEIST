"""Firewall puzzle: a Mastermind-style ordered sequence of fictional rule tokens."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from core.rng import GameRNG

RULE_POOL = [
    "ALLOW_SSH_DECOY", "DENY_RELAY", "DROP_ICMP_ECHO", "PASS_NTP_SYNC",
    "BLOCK_TELNET_X", "ROUTE_VPN_SHADOW", "LOG_DNS_TRACE", "FLUSH_ARP_CACHE",
]


def score(secret: tuple[int, ...], guess: tuple[int, ...]) -> tuple[int, int]:
    """Return (exact, partial): right token in right slot, right token in wrong slot."""
    exact = sum(s == g for s, g in zip(secret, guess))
    common = len(set(secret) & set(guess))
    return exact, common - exact


def solve(secret: tuple[int, ...], pool_size: int, length: int) -> list[tuple[int, ...]]:
    """Play with a first-consistent-candidate strategy; return the guesses made."""
    candidates = list(permutations(range(pool_size), length))
    guesses: list[tuple[int, ...]] = []
    while True:
        guess = candidates[0]
        guesses.append(guess)
        fb = score(secret, guess)
        if fb[0] == length:
            return guesses
        candidates = [c for c in candidates if score(c, guess) == fb]


@dataclass
class FirewallPuzzle:
    """One firewall lock. Tokens are indices into ``pool``; repeats are not allowed."""

    pool: list[str]
    secret: tuple[int, ...]
    attempts: int
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
        if len(set(idx)) != len(idx):
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
        for cand in permutations(range(len(self.pool)), self.length):
            if all(score(cand, g) == fb for g, fb in self.history):
                return " ".join(str(i + 1) for i in cand)
        return " ".join(str(i + 1) for i in self.secret)


def generate(rng: GameRNG, pool_size: int, length: int, attempts: int) -> FirewallPuzzle:
    """Create a puzzle guaranteed solvable: attempts are raised to what the solver needs."""
    pool_size = max(6, min(len(RULE_POOL), pool_size))
    length = max(3, min(pool_size - 1, length))
    pool = rng.sample(RULE_POOL, pool_size)
    secret = tuple(rng.sample(range(pool_size), length))
    needed = len(solve(secret, pool_size, length))
    return FirewallPuzzle(pool=pool, secret=secret, attempts=max(attempts, needed))
