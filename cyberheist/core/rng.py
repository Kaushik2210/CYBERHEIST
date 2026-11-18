"""Seeded random number generation.

Every random decision in CYBERHEIST goes through :class:`GameRNG` so that a run
started with ``--seed N`` is fully reproducible.
"""
from __future__ import annotations

import random
import zlib
from typing import MutableSequence, Sequence, TypeVar

T = TypeVar("T")


class GameRNG:
    """A thin, seedable wrapper around :class:`random.Random`."""

    def __init__(self, seed: int | None = None) -> None:
        """Create an RNG. With ``seed=None`` a fresh seed is drawn from the OS."""
        if seed is None:
            seed = random.SystemRandom().randrange(1, 2**31 - 1)
        self.seed: int = int(seed)
        self._rand = random.Random(self.seed)

    def fork(self, label: str) -> "GameRNG":
        """Return a child RNG derived deterministically from this seed and ``label``.

        Forking keeps sub-systems independent: generating an extra event roll does
        not change which puzzle a later stage receives.
        """
        child_seed = zlib.crc32(f"{self.seed}:{label}".encode("utf-8")) & 0x7FFFFFFF
        return GameRNG(child_seed or 1)

    def randint(self, a: int, b: int) -> int:
        """Return a random integer N such that ``a <= N <= b``."""
        return self._rand.randint(a, b)

    def random(self) -> float:
        """Return a float in ``[0, 1)``."""
        return self._rand.random()

    def chance(self, p: float) -> bool:
        """Return True with probability ``p``."""
        return self._rand.random() < p

    def choice(self, seq: Sequence[T]) -> T:
        """Return one random element of a non-empty sequence."""
        return self._rand.choice(seq)

    def sample(self, seq: Sequence[T], k: int) -> list[T]:
        """Return ``k`` unique elements chosen from ``seq``."""
        return self._rand.sample(list(seq), k)

    def shuffle(self, seq: MutableSequence[T]) -> None:
        """Shuffle ``seq`` in place."""
        self._rand.shuffle(seq)
