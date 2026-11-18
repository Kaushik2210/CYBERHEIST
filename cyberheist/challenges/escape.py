"""Escape sequence: quick rounds against a tick countdown after the objective is done.

Easy rounds: pick the lane the beacon names, or retype a code you can see.
Tough rounds (Normal and Hard): memorise a code or a lane sequence before the screen
clears, or work out the exit lane from a clue.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cyberheist.core.rng import GameRNG

LANES = ["BLUE", "RED", "GREEN", "AMBER", "VIOLET", "WHITE"]
WARM = {"RED", "AMBER"}
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def lane_initials(text: str) -> str | None:
    """Turn 'BLUE RED', 'B R' or 'BR' into 'BR'. None if any part isn't a lane."""
    names = {lane: lane[0] for lane in LANES}
    initials = set(names.values())
    parts = text.strip().upper().replace(",", " ").split()
    if len(parts) == 1 and len(parts[0]) > 1 and parts[0] not in names:
        parts = list(parts[0])
    out = []
    for p in parts:
        if p in names:
            out.append(names[p])
        elif len(p) == 1 and p in initials:
            out.append(p)
        else:
            return None
    return "".join(out)


@dataclass
class EscapeRound:
    """One round. ``memorize`` is shown, then cleared, before the prompt."""

    kind: str
    prompt: str
    options: list[str]
    answer: str
    memorize: str = ""

    def is_correct(self, text: str) -> bool:
        """Check an answer: option number or name, a code, or a lane sequence."""
        text = text.strip().upper()
        if self.kind in ("choice", "clue") and text.isdigit():
            i = int(text) - 1
            return 0 <= i < len(self.options) and self.options[i] == self.answer
        if self.kind == "sequence":
            return lane_initials(text) == lane_initials(self.answer)
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


def _code(rng: GameRNG, n: int) -> str:
    return "".join(rng.choice(CODE_CHARS) for _ in range(n))


def _easy_round(rng: GameRNG) -> EscapeRound:
    if rng.chance(0.5):
        lanes = rng.sample(LANES, 3)
        correct = rng.choice(lanes)
        return EscapeRound("choice", f"Exit beacon reads {correct}. Which lane?", lanes, correct)
    code = _code(rng, 4)
    return EscapeRound("code", f"Retype the exit code: {code}", [], code)


def _clue_round(rng: GameRNG) -> EscapeRound:
    """Three lanes and a clue that fits exactly one of them."""
    while True:
        lanes = rng.sample(LANES, 3)
        clues = []
        warm = [x for x in lanes if x in WARM]
        if len(warm) == 1:
            clues.append(("The exit is the only warm-coloured lane.", warm[0]))
        if len(warm) == 2:
            cool = [x for x in lanes if x not in WARM][0]
            clues.append(("The exit is the only cool-coloured lane.", cool))
        for lane in lanes:
            if sum(len(x) == len(lane) for x in lanes) == 1:
                clues.append((f"The exit lane's name has {len(lane)} letters.", lane))
        clues.append(("The exit lane comes first alphabetically.", min(lanes)))
        clues.append(("The exit lane comes last alphabetically.", max(lanes)))
        text, answer = rng.choice(clues)
        if [x for x in lanes if x == answer]:
            return EscapeRound("clue", f"{text} Which lane?", lanes, answer)


def _tough_round(rng: GameRNG, hard: bool) -> EscapeRound:
    kind = rng.choice(["memory", "sequence", "clue"])
    if kind == "memory":
        code = _code(rng, 6 if hard else 5)
        return EscapeRound("memory", "Type the exit code you just saw.", [], code, memorize=f"EXIT CODE: {code}")
    if kind == "sequence":
        seq = [rng.choice(LANES)]
        while len(seq) < (4 if hard else 3):
            seq.append(rng.choice([x for x in LANES if x != seq[-1]]))   # no back-to-back repeats
        return EscapeRound("sequence", "Repeat the lane sequence (names or initials, e.g. B R G).", [],
                           " ".join(seq), memorize="LANES: " + "  ".join(seq))
    return _clue_round(rng)


def generate(rng: GameRNG, rounds: int = 3, slack: int = 4, round_cost: int = 2,
             fail_cost: int = 2, tough: bool = False, hard: bool = False) -> EscapeSequence:
    """Build a sequence. Perfect play always fits inside the countdown."""
    rounds = max(1, rounds)
    built = [_tough_round(rng, hard) if tough else _easy_round(rng) for _ in range(rounds)]
    countdown = rounds * round_cost + max(0, slack)
    return EscapeSequence(built, countdown, round_cost, fail_cost)
