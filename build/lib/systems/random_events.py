"""Seeded random events, rolled once per block of ticks. Events can never make a mission unwinnable."""
from __future__ import annotations

from typing import Any

from core.rng import GameRNG

EVENT_ORDER = ("firewall_update", "security_patrol", "encrypted_backup", "suspicious_traffic",
               "hidden_intel", "exposed_vulnerability", "anonymous_message")
MESSAGES = [
    "ANON: 'Someone on your crew talks too much. Watch your back.'",
    "ANON: 'VANTA isn't who you think.'",
    "ANON: 'ORACLE pays well. Ask why.'",
    "ANON: 'Check who knew your route before you did.'",
]


class EventEngine:
    """Rolls at most one event each time the clock crosses a tick block."""

    def __init__(self, cfg: dict[str, Any], rng: GameRNG) -> None:
        """Create the engine from the ``events`` block of settings.json."""
        self.cfg = cfg
        self.block = max(1, int(cfg["block_ticks"]))
        self.prob = cfg["probabilities"]
        self.rng = rng
        self.fired: list[str] = []

    def on_ticks(self, ctx: Any, before: float, after: float) -> list[str]:
        """Roll for every block boundary crossed between ``before`` and ``after``."""
        out = []
        for _ in range(int(after // self.block) - int(before // self.block)):
            for eid in EVENT_ORDER:
                if self.rng.chance(self.prob.get(eid, 0.0)):
                    out.append(self.fire(ctx, eid))
                    break
        return out

    def fire(self, ctx: Any, eid: str) -> str:
        """Apply one event to the mission context and report it."""
        self.fired.append(eid)
        ui = ctx.ui
        if eid == "firewall_update":
            headroom = max(0.0, ctx.max_ticks - ctx.ticks - 1)
            cost = min(float(self.cfg["firewall_update_ticks"]), headroom)
            ctx.ticks += cost
            msg = f"EVENT: Firewall rules updated. Re-scanning cost {cost:.0f} ticks."
            ui.warn(msg)
        elif eid == "security_patrol":
            level_before = ctx.meter.level
            added, absorbed = ctx.meter.alarm()
            ceiling = ctx.cfg["detection"]["event_ceiling"]
            if ctx.meter.level > ceiling:
                ctx.meter.level = max(level_before, float(ceiling))
            msg = ("EVENT: Security patrol. Signal Mask absorbed the alarm." if absorbed
                   else f"EVENT: Security patrol sweep. Detection +{ctx.meter.level - level_before:.0f}.")
            ui.warn(msg)
        elif eid == "encrypted_backup":
            ctx.bonus_credits += int(self.cfg["backup_credits"])
            msg = f"EVENT: Encrypted backup found. +{self.cfg['backup_credits']} cr on completion."
            ui.ok(msg)
        elif eid == "suspicious_traffic":
            msg = "EVENT: Suspicious traffic on the wire. Nothing flagged you. Yet."
            ui.info(msg)
        elif eid == "hidden_intel":
            ctx.free_reveals += 1
            msg = "EVENT: Hidden intel recovered. Type 'use intel' to reveal a puzzle detail."
            ui.ok(msg)
        elif eid == "exposed_vulnerability":
            ctx.free_hints += 1
            msg = "EVENT: Exposed vulnerability. Your next cipher 'hint' is free."
            ui.ok(msg)
        else:
            msg = self.rng.choice(MESSAGES)
            ui.say(msg, "accent")
        return msg
