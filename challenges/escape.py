"""Escape sequence: quick rounds against a tick countdown after the objective is done."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.rng import GameRNG

LANES = ["BLUE", "RED", "GREEN", "AMBER", "VIOLET", "WHITE"]
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class EscapeRound:
    """One round: pick the matching option, or retype a displayed code."""

    kind: str
    prompt: str
    options: list[str]
    answer: str

    def is_correct(self, text: str) -> bool:
        """Accept the option number or its text (choice), or the exact code (case-insensitive)."""
        text = text.strip().upper()
        if self.kind == "choice" and text.isdigit():
            i = int(text) - 1
            return 0 <= i < len(self.options) and self.options[i] == self.answer
        return text == self.answer


@dataclass
class EscapeSequence:
    """A run of rounds that must all be cleared before the countdown reaches zero."""

    rounds: list[EscapeRound]
    countdown: int
    round_cost: int = 2
    fail_cost: int = 2
    index: int = 0
    elapsed: int = 0
    failures: int = 0
    history: list[bool] = field(default_factory=list)

    @property
    def current(self) -> EscapeRound | None:
        """The round in play, or None when all are cleared."""
        return self.rounds[self.index] if self.index < len(self.rounds) else None

    @property
    def ticks_left(self) -> int:
        """Countdown remaining."""
        return self.countdown - self.elapsed

    @property
    def escaped(self) -> bool:
        """True when every round was cleared in time."""
        return self.index >= len(self.rounds) and self.ticks_left >= 0

    @property
    def out_of_time(self) -> bool:
        """True when the countdown ran out first."""
        return self.ticks_left < 0 or (self.ticks_left == 0 and self.index < len(self.rounds))

    def answer(self, text: str) -> bool:
        """Play the current round. A miss costs extra ticks and the round repeats."""
        rnd = self.current
        if rnd is None:
            return True
        ok = rnd.is_correct(text)
        self.history.append(ok)
        self.elapsed += self.round_cost
        if ok:
            self.index += 1
        else:
            self.failures += 1
            self.elapsed += self.fail_cost
        return ok

    def solver_answer(self) -> str:
        """Autopilot answer for the current round."""
        rnd = self.current
        return rnd.answer if rnd else ""


def _make_round(rng: GameRNG) -> EscapeRound:
    if rng.chance(0.5):
        lanes = rng.sample(LANES, 3)
        correct = rng.choice(lanes)
        return EscapeRound("choice", f"Exit beacon reads {correct}. Which lane?", lanes, correct)
    code = "".join(rng.choice(CODE_CHARS) for _ in range(4))
    return EscapeRound("code", f"Retype the exit code: {code}", [], code)


def generate(rng: GameRNG, rounds: int = 3, slack: int = 4, round_cost: int = 2,
             fail_cost: int = 2) -> EscapeSequence:
    """Build a sequence. Perfect play always fits inside the countdown."""
    rounds = max(1, rounds)
    built = [_make_round(rng) for _ in range(rounds)]
    countdown = rounds * round_cost + max(0, slack)
    return EscapeSequence(built, countdown, round_cost, fail_cost)
