"""Run debrief: what each stage cost, how it compared with the solver, and what to try next.

The stage players record raw facts into a ``StageLog``; ``summarize`` turns a log into
short fact lines and tips (most useful first). Nothing here touches the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChainLog:
    """One guess-and-feedback lock: a firewall chain, a network lock or a passphrase."""

    name: str
    par: int
    used: int = 0
    solved: bool = False
    careless: list[tuple[int, int]] = field(default_factory=list)  # (probe, probe it contradicted)
    noun: str = "probe"


@dataclass
class StageLog:
    """Everything the debrief needs about one stage."""

    kind: str
    label: str
    ticks: float = 0.0
    detection: float = 0.0
    wrong: int = 0
    cleared: bool = False
    chains: list[ChainLog] = field(default_factory=list)
    hints: int = 0
    tools: int = 0
    tough: bool = False
    scans: int = 0
    scans_needed: int = 0
    route: dict[str, Any] | None = None
    rounds: int = 0
    misses: list[str] = field(default_factory=list)
    commands: int = 0

    @property
    def par_cell(self) -> str:
        """'used/par' for the main lock, for the run summary table."""
        main = next((c for c in self.chains if c.name in ("Firewall", "Passphrase")), None)
        return f"{main.used}/{main.par}" if main else "-"


def _plural(n: int, word: str) -> str:
    if n == 1:
        return f"{n} {word}"
    return f"{n} {word}{'es' if word.endswith('s') else 's'}"


ESCAPE_TIPS = {
    "memory": "Missed a memory code: read it in chunks of two or three characters and say them.",
    "sequence": "Missed a lane sequence: say the initials as one word (G-R-A-B) before it clears.",
    "clue": "Missed a clue round: rule lanes out one clue at a time; the answer is the one left.",
}


def _chain(c: ChainLog, facts: list[str], tips: list[str]) -> None:
    if not c.solved:
        facts.append(f"{c.name}: locked out after {_plural(c.used, c.noun)} (solver par {c.par})")
    elif c.used < c.par:
        facts.append(f"{c.name}: {_plural(c.used, c.noun)}, solver par {c.par} (beat it by {c.par - c.used})")
    elif c.used == c.par:
        facts.append(f"{c.name}: {_plural(c.used, c.noun)}, solver par {c.par} (matched)")
    else:
        facts.append(f"{c.name}: {_plural(c.used, c.noun)}, solver par {c.par} (+{c.used - c.par})")
    if c.careless:
        probe, against = c.careless[0]
        facts.append(f"{c.name}: {_plural(len(c.careless), 'careless ' + c.noun)} "
                     f"(full detection{' each' if len(c.careless) > 1 else ''})")
        tips.append(f"{c.name}: {c.noun} {probe} contradicted the feedback from {c.noun} {against}, so it "
                    f"could not have been the answer. Check each {c.noun} against every earlier result.")
    elif c.solved and c.used > c.par:
        tips.append(f"{c.name}: every {c.noun} fit the clues; the extra {c.used - c.par} came down to which "
                    f"candidate you tried. Pick ones that also test "
                    + ("characters you haven't tried yet." if c.noun == "guess" else "rules you haven't placed yet."))


def summarize(log: StageLog, det: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Fact lines and tips for one stage. Tips are ordered most useful first."""
    facts: list[str] = []
    tips: list[str] = []
    for c in log.chains:
        _chain(c, facts, tips)
    if log.kind == "cipher":
        bits = [_plural(log.wrong, "wrong decode") if log.wrong else "decoded first time"]
        if log.hints:
            bits.append(_plural(log.hints, "hint"))
        if log.tools:
            bits.append(_plural(log.tools, "lab tool use"))
        facts.append(", ".join(bits))
        if log.wrong:
            tool = f"+{det['lab_tool']}" if log.tough else "nothing"
            tips.append(f"A wrong decode costs +{det['wrong_guess']} detection; a lab tool costs {tool}. "
                        "Test with 'shift N', 'apply KEY' or 'unhex' before you submit.")
    elif log.kind == "network":
        if log.route:
            r = log.route
            facts.append(f"{_plural(log.scans, 'scan')}, route {r['rating']} risk (+{r['added']} detection)")
            if r["best_rating"] != r["rating"] and r["label"] != r["best_label"]:
                lock = (" It was locked, but cracking a 3-rule lock usually costs less than a risky route."
                        if r["best_locked"] else "")
                tips.append(f"A {r['best_rating']} risk route existed: {r['best_label']}.{lock}")
        if log.tough and log.scans and log.detection >= 20:
            tips.append(f"Scans cost +{det['network_scan']} detection each here, double for hidden-node "
                        "layers. A Data Scanner from the black market reveals hidden nodes for free.")
        if log.scans < log.scans_needed:
            tips.append(f"You routed after {log.scans} of {log.scans_needed} scans. The full map can hold "
                        "hidden nodes with safer paths.")
    elif log.kind == "escape" and log.rounds:
        facts.append(f"{log.rounds - len(log.misses)}/{log.rounds} rounds first time")
        for kind in dict.fromkeys(log.misses):
            tips.append(ESCAPE_TIPS.get(kind, "Missed a round: each miss costs ticks and detection."))
    elif log.kind == "shell" and log.commands:
        facts.append(f"{_plural(log.commands, 'command')} (minimum 3: scan, connect, cat)")
    return facts, tips


def biggest_leak(logs: list[StageLog]) -> StageLog | None:
    """The stage that added the most detection, if any added some."""
    worst = max(logs, key=lambda s: s.detection, default=None)
    return worst if worst is not None and worst.detection > 0 else None
