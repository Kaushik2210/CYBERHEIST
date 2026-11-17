"""Network mapping: discover a generated topology layer by layer, then choose a route."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.rng import GameRNG

START = "INTERNET"
BASE_EDGES = [
    ("INTERNET", "FIREWALL"), ("FIREWALL", "GATEWAY"), ("GATEWAY", "SERVER-A"),
    ("GATEWAY", "SERVER-B"), ("SERVER-A", "DATABASE"), ("SERVER-B", "BACKUP"), ("BACKUP", "DATABASE"),
]
HIDDEN = {
    "RELAY-7": [("INTERNET", "RELAY-7"), ("RELAY-7", "GATEWAY")],
    "PROXY-X": [("SERVER-B", "PROXY-X"), ("PROXY-X", "DATABASE")],
}


@dataclass
class Route:
    """One path through discovered nodes."""

    nodes: list[str]
    risk: int
    rating: str


@dataclass
class NetworkMap:
    """A generated topology plus what the player has discovered."""

    edges: dict[frozenset, int]
    hidden: set[str]
    target: str
    discovered: set[str] = field(default_factory=lambda: {START})
    scans: int = 0

    @property
    def nodes(self) -> set[str]:
        """Every node in the topology."""
        return {n for e in self.edges for n in e}

    def neighbors(self, node: str) -> set[str]:
        """Nodes directly linked to ``node``."""
        return {m for e in self.edges if node in e for m in e if m != node}

    def scan(self) -> list[str]:
        """Reveal the next layer. Hidden nodes only show once every visible node is known."""
        self.scans += 1
        visible = self.nodes - self.hidden
        frontier = {m for n in self.discovered for m in self.neighbors(n)} - self.discovered
        found = frontier & visible
        if not found and visible <= self.discovered:
            found = frontier & self.hidden
        self.discovered |= found
        return sorted(found)

    @property
    def fully_mapped(self) -> bool:
        """True when every node has been discovered."""
        return self.discovered >= self.nodes

    def routes(self) -> list[Route]:
        """All simple paths from INTERNET to the target over discovered nodes, safest first."""
        out: list[Route] = []

        def walk(path: list[str]) -> None:
            node = path[-1]
            if node == self.target:
                risk = sum(self.edges[frozenset(p)] for p in zip(path, path[1:]))
                out.append(Route(list(path), risk, _rating(risk, len(path) - 1)))
                return
            for nxt in sorted(self.neighbors(node) & self.discovered):
                if nxt not in path:
                    walk(path + [nxt])

        if self.target in self.discovered:
            walk([START])
        return sorted(out, key=lambda r: (r.risk, len(r.nodes), r.nodes))

    def found_hidden(self) -> bool:
        """True if any hidden node has been discovered."""
        return bool(self.hidden & self.discovered)

    def solver_commands(self) -> list[str]:
        """Autopilot: scan until the map is complete, then take the safest route."""
        cmds = []
        probe = NetworkMap(dict(self.edges), set(self.hidden), self.target, set(self.discovered), self.scans)
        while not probe.fully_mapped:
            probe.scan()
            cmds.append("scan")
        cmds.append("route 1")
        return cmds


def _rating(risk: int, hops: int) -> str:
    avg = risk / max(1, hops)
    if avg <= 1.5:
        return "LOW"
    if avg <= 2.3:
        return "MEDIUM"
    return "HIGH"


def route_detection(rating: str, rng: GameRNG, cfg: dict[str, Any]) -> int:
    """Detection added for taking a route of this rating (risky routes: +10 to +20)."""
    if rating == "HIGH":
        return rng.randint(cfg["risky_route_min"], cfg["risky_route_max"])
    if rating == "MEDIUM":
        return int(cfg["medium_route"])
    return 0


def generate(rng: GameRNG, target: str = "DATABASE", hidden_nodes: int = 1) -> NetworkMap:
    """Build a topology. The base graph always links INTERNET to every target."""
    edges = {frozenset(e): rng.randint(1, 3) for e in BASE_EDGES}
    chosen = rng.sample(sorted(HIDDEN), max(0, min(len(HIDDEN), hidden_nodes)))
    for name in chosen:
        for e in HIDDEN[name]:
            edges[frozenset(e)] = 1
    return NetworkMap(edges=edges, hidden=set(chosen), target=target)
