"""Mission runner: tick clock, detection, the HUD, and the interactive loop for each stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from challenges import encryption, escape, firewall, network, password
from challenges.detection import DetectionMeter
from core.rng import GameRNG
from core.state import MissionAborted, MissionFailed
from interface import screens
from interface.ui import UI
from systems.inventory import Inventory
from systems.random_events import EventEngine

ITEM_ALIASES = {
    "toolkit": "cipher_toolkit", "cipher": "cipher_toolkit",
    "decoder": "quantum_decoder", "quantum": "quantum_decoder",
    "scanner": "data_scanner", "override": "emergency_override",
}
ALIASES_BY_ID = {"cipher_toolkit": "toolkit", "quantum_decoder": "decoder",
                 "data_scanner": "scanner", "emergency_override": "override"}


class MissionContext:
    """Shared state for one mission run."""

    def __init__(self, ui: UI, rng: GameRNG, cfg: dict[str, Any], difficulty: str = "normal",
                 grace_ticks: int = 40, max_ticks: int = 200, neural: bool = False,
                 ghost_proxy: bool = False, signal_mask: bool = False,
                 inventory: Inventory | None = None, events: bool = False) -> None:
        """Set up the clock and the detection meter. Equipped passives in ``inventory`` apply.

        With ``events=True`` seeded random events roll once per tick block.
        """
        self.inventory = inventory
        self.events = EventEngine(cfg["events"], rng.fork("events")) if events else None
        self.bonus_credits = 0
        self.free_hints = 0
        self.free_reveals = 0
        if inventory is not None:
            gear = inventory.loadout()
            neural = neural or gear["neural"]
            ghost_proxy = ghost_proxy or gear["ghost_proxy"]
            signal_mask = signal_mask or gear["signal_mask"]
        self.items_used: list[str] = []
        self.solved: dict[str, int] = {}
        self.puzzle: Any = None
        self.stage_kind = ""
        self.ui, self.rng, self.cfg = ui, rng, cfg
        self.diff = cfg["difficulty"][difficulty]
        self.meter = DetectionMeter(cfg["detection"], self.diff["detection_mult"], ghost_proxy, signal_mask)
        self.tick_cfg = cfg["ticks"]
        self.tick_mult = self.tick_cfg["neural_mult"] if neural else 1.0
        self.grace = max(5, grace_ticks + self.diff["grace_bonus"])
        self.max_ticks = max_ticks
        self.ticks = 0.0
        self.wrong_guesses = 0
        self.objective = ""
        self.help_text = ""
        self.found_hidden = False
        self.patrol_rate = 0.0

    # -- clock & detection -------------------------------------------------------
    def spend(self, kind: str = "command", count: float = 1) -> None:
        """Spend ticks; time past the grace period raises detection, as does an active patrol."""
        before = self.ticks
        cost = self.tick_cfg[kind] * count * self.tick_mult
        self.ticks += cost
        over = max(0.0, self.ticks - max(before, self.grace))
        if over:
            self.meter.overtime(over)
        if self.patrol_rate:
            self.meter.add(self.patrol_rate * cost)
        if self.events is not None:
            self.events.on_ticks(self, before, self.ticks)
        self.check()

    def wrong(self) -> None:
        """Penalty for a wrong guess: detection and extra ticks."""
        self.wrong_guesses += 1
        self.meter.wrong_guess()
        self.spend("wrong_guess")

    def check(self) -> None:
        """Raise MissionFailed when a failure condition is met."""
        if self.meter.failed:
            raise MissionFailed("Detection reached 100%. Trace complete.")
        if self.ticks > self.max_ticks:
            raise MissionFailed("Tick budget exhausted. The window closed.")

    def cooldown(self) -> None:
        """Clearing a stage lets the trace cool off a little."""
        self.meter.reduce(self.cfg["detection"]["stage_cooldown"])

    # -- HUD & input ---------------------------------------------------------------
    def hud(self) -> None:
        """Print the one-line heads-up display."""
        m = self.meter
        bar = self.ui.bar(m.level, 100, 20, m.role)
        self.ui.say(f"DET {bar} {m.level:5.1f}% {self.ui.paint(m.status, m.role)} | "
                    f"TICKS {self.ticks:.0f}/{self.max_ticks} (grace {self.grace}) | {self.objective}")

    def ask(self, label: str, auto: Callable[[], str] | None = None) -> str:
        """Prompt, handling the shared commands: '?', 'status', 'b'."""
        while True:
            raw = self.ui.prompt(label, auto)
            cmd = raw.strip().lower()
            if cmd in ("?", "help"):
                self.ui.info(self.help_text or "Type an answer, 'status' for the HUD.")
            elif cmd == "status":
                self.hud()
            elif cmd == "b":
                self.ui.warn("No going back mid-stage. Finish it, or wait for the stage break.")
            elif cmd in ("inv", "items"):
                self.show_items()
            elif cmd.startswith("use "):
                self.use_item(cmd[4:].strip())
            elif cmd:
                return raw.strip()

    # -- items ---------------------------------------------------------------------
    def show_items(self) -> None:
        """List consumables and equipped gear."""
        inv = self.inventory
        if inv is None or not inv.rows:
            self.ui.info("Inventory empty. Visit the black market between missions.")
            return
        gear = [inv.cfg[i]["name"] for i in inv.equipped()]
        cons = [f"{inv.cfg[i]['name']} x{inv.uses(i)} (use {ALIASES_BY_ID[i]})"
                for i in inv.rows if inv.kind(i) == "consumable"]
        self.ui.info("Equipped: " + (", ".join(gear) or "none"))
        self.ui.info("Consumables: " + (", ".join(cons) or "none"))

    def use_item(self, name: str) -> bool:
        """Use a consumable on the current stage. Charges are spent only when it has an effect."""
        if name == "intel":
            if self.free_reveals <= 0:
                self.ui.warn("No banked intel. Hidden intel events add some.")
                return False
            message = self._apply_item("quantum_decoder")
            if message is None:
                self.ui.warn("Intel has no use on this stage. Kept for later.")
                return False
            self.free_reveals -= 1
            self.ui.ok(message.replace("Decoder", "Intel"))
            return True
        iid = ITEM_ALIASES.get(name, name)
        inv = self.inventory
        if inv is None or iid not in inv.cfg or inv.kind(iid) != "consumable":
            self.ui.warn("Usable items: toolkit, decoder, scanner, override.")
            return False
        if not inv.owns(iid):
            self.ui.warn(f"You have no {inv.cfg[iid]['name']} left.")
            return False
        message = self._apply_item(iid)
        if message is None:
            self.ui.warn(f"{inv.cfg[iid]['name']} has no effect here. Charge kept.")
            return False
        inv.consume(iid)
        self.items_used.append(iid)
        self.ui.ok(message)
        return True

    def _apply_item(self, iid: str) -> str | None:
        p, kind = self.puzzle, self.stage_kind
        if iid == "cipher_toolkit" and kind == "cipher":
            hint = p.next_hint()
            return f"Toolkit hint: {hint}" if hint else None
        if iid == "quantum_decoder":
            if kind == "firewall":
                got = p.reveal_slot()
                return f"Decoder: slot {got[0] + 1} is {p.pool[got[1]]}." if got else None
            if kind == "password":
                got = p.reveal_position()
                return f"Decoder: character {got[0] + 1} is '{got[1]}'." if got else None
            if kind == "cipher":
                return f"Decoder: {p.reveal_detail()}"
        if iid == "emergency_override" and kind in ("firewall", "password", "cipher"):
            p.add_attempt()
            return f"Override: +1 attempt ({p.remaining} left)."
        return None


# -- stage players -------------------------------------------------------------------
def play_firewall(ctx: MissionContext, params: dict[str, Any]) -> None:
    """Interactive firewall stage."""
    d = ctx.diff
    p = firewall.generate(ctx.rng.fork("firewall"), params.get("pool", 6),
                          params.get("length", 4) + d["code_length_delta"],
                          params.get("attempts", 8) + d["attempt_bonus"])
    ctx.puzzle, ctx.stage_kind = p, "firewall"
    ctx.objective = f"Crack the {p.length}-rule firewall chain"
    ctx.help_text = "Enter rule numbers in order, e.g. '1 4 2 6'. Exact = right rule, right slot."
    ctx.ui.box("FIREWALL", [f"{i + 1}. {r}" for i, r in enumerate(p.pool)])
    while not p.solved:
        if p.remaining <= 0:
            raise MissionFailed("Firewall locked out: no attempts left.")
        ctx.hud()
        raw = ctx.ask(f"chain ({p.remaining} left)", p.next_solver_guess)
        parsed = p.parse(raw)
        if isinstance(parsed, str):
            ctx.ui.warn(parsed)
            continue
        exact, partial = p.guess(parsed)
        ctx.spend()
        if p.solved:
            ctx.ui.ok("Firewall chain accepted.")
        else:
            ctx.ui.say(f"  exact {exact}  partial {partial}", "accent")
            ctx.wrong()


def play_cipher(ctx: MissionContext, params: dict[str, Any]) -> None:
    """Interactive encryption-lab stage."""
    p = encryption.generate(ctx.rng.fork(f"cipher-{params['kind']}"), params["kind"],
                            params.get("attempts", 3) + max(0, ctx.diff["attempt_bonus"]))
    ctx.puzzle, ctx.stage_kind = p, "cipher"
    ctx.objective = f"Decode the {p.kind} intercept"
    ctx.help_text = "Type the plaintext. 'hint' costs ticks; 'shift N' / 'apply KEY' are lab tools."
    ctx.ui.box(f"CIPHER LAB: {p.kind.upper()}", [p.brief, "", p.ciphertext])
    while not p.solved:
        if p.remaining <= 0:
            raise MissionFailed("Cipher lab locked: too many wrong decodes.")
        ctx.hud()
        raw = ctx.ask(f"decode ({p.remaining} left)", p.solver_answer)
        low = raw.lower()
        if low == "hint":
            hint = p.next_hint()
            ctx.ui.info(hint or "No hints left.")
            if hint and ctx.free_hints > 0:
                ctx.free_hints -= 1
                ctx.ui.ok("Free hint from the exposed vulnerability.")
            elif hint:
                ctx.spend("hint")
        elif low.startswith(("shift ", "apply ")):
            ctx.ui.say(p.tool(raw.split(None, 1)[1]), "accent")
            ctx.spend("tool")
        elif p.check(raw):
            ctx.spend()
            ctx.ui.ok("Plaintext confirmed.")
        else:
            ctx.ui.warn("That doesn't decode cleanly.")
            ctx.wrong()


def play_password(ctx: MissionContext, params: dict[str, Any]) -> None:
    """Interactive password stage."""
    p = password.generate(ctx.rng.fork("password"), params.get("words", 8), params.get("digits", 2),
                          params.get("symbols", 4), params.get("range", 3),
                          params.get("attempts", 6) + ctx.diff["attempt_bonus"])
    ctx.puzzle, ctx.stage_kind = p, "password"
    ctx.objective = "Recover the passphrase"
    ctx.help_text = "Marks: + right place, ~ elsewhere in the password, . not in it."
    ctx.ui.box("PASSPHRASE", p.clues())
    while not p.solved:
        if p.remaining <= 0:
            raise MissionFailed("Account locked: no attempts left.")
        ctx.hud()
        raw = ctx.ask(f"passphrase ({p.remaining} left)", p.next_solver_guess)
        err = p.validate(raw)
        if err:
            ctx.ui.warn(err)
            continue
        marks = p.guess(raw)
        ctx.spend()
        if p.solved:
            ctx.ui.ok("Passphrase accepted.")
        else:
            ctx.ui.say(f"  {raw.upper()}\n  {marks}", "accent")
            ctx.wrong()


def play_network(ctx: MissionContext, params: dict[str, Any]) -> None:
    """Interactive network-mapping stage."""
    m = network.generate(ctx.rng.fork("network"), params.get("target", "DATABASE"), params.get("hidden", 1))
    ctx.objective = f"Map the network and route to {m.target}"
    ctx.help_text = "'scan' reveals the next layer (costs ticks). 'routes' lists paths. 'route N' commits. 'map' draws the map."
    plan = iter(m.solver_commands())
    while True:
        ctx.hud()
        cmd = ctx.ask("net", lambda: next(plan, "route 1")).lower()
        if cmd == "scan":
            found = m.scan()
            ctx.spend("scan")
            ctx.ui.say("  found: " + (", ".join(found) if found else "nothing new"), "accent")
        elif cmd == "map":
            screens.network_map(ctx.ui, m)
        elif cmd == "routes":
            rows = [(i + 1, " > ".join(r.nodes), r.risk, r.rating) for i, r in enumerate(m.routes())]
            if rows:
                ctx.ui.table(["#", "ROUTE", "RISK", "RATING"], rows)
            else:
                ctx.ui.warn(f"{m.target} not found yet. Keep scanning.")
        elif cmd.startswith("route "):
            routes = m.routes()
            try:
                r = routes[int(cmd.split()[1]) - 1]
            except (ValueError, IndexError):
                ctx.ui.warn("Pick a route number from 'routes'.")
                continue
            ctx.meter.add(network.route_detection(r.rating, ctx.rng.fork("route"), ctx.cfg["detection"]))
            ctx.spend()
            ctx.found_hidden = m.found_hidden()
            ctx.ui.ok(f"Routed via {' > '.join(r.nodes)} ({r.rating} risk).")
            return
        else:
            ctx.ui.warn("Commands: scan, map, routes, route N.")


def play_escape(ctx: MissionContext, params: dict[str, Any]) -> None:
    """Interactive escape stage."""
    seq = escape.generate(ctx.rng.fork("escape"), params.get("rounds", 3),
                          params.get("slack", 4) + max(0, ctx.diff["attempt_bonus"]))
    ctx.objective = "Get out before the countdown ends"
    ctx.help_text = "Answer each round: an option number, or the code exactly."
    while not seq.escaped:
        if seq.out_of_time:
            raise MissionFailed("Countdown expired before you got out.")
        rnd = seq.current
        ctx.ui.say(f"[{seq.ticks_left} ticks] {rnd.prompt}", "warn")
        for i, opt in enumerate(rnd.options, 1):
            ctx.ui.say(f"  {i}. {opt}")
        ok = seq.answer(ctx.ask("escape", seq.solver_answer))
        ctx.spend("escape_round")
        if not ok:
            ctx.ui.warn("Missed. The countdown keeps running.")
            ctx.meter.add(ctx.cfg["detection"]["escape_fail"])
            ctx.check()
    ctx.ui.ok("Clean exit.")


SHELL_HOST = "train-01"
SHELL_FILES = {
    "welcome.txt": "Welcome, operator. Training flag: GHOST-ZERO. You passed orientation.",
    "notes.txt": "Reminder: every command costs a tick. Watch the clock.",
}


def play_shell(ctx: MissionContext, params: dict[str, Any]) -> None:
    """Tutorial shell: learn help, scan, connect, ls, cat and status on a training node."""
    ctx.objective = f"Find {SHELL_HOST} and read welcome.txt"
    ctx.help_text = "Commands: help, scan, connect <host>, ls, cat <file>, status."
    ctx.ui.box("TRAINING SHELL", ["This is a sandbox. Type 'help' to see the commands.",
                                  "Goal: find the training node, connect, and read welcome.txt."])
    found = connected = False
    plan = iter(["help", "scan", f"connect {SHELL_HOST}", "ls", "cat welcome.txt"])
    while True:
        cmd = ctx.ask("shell", lambda: next(plan, "cat welcome.txt"))
        verb, _, arg = cmd.partition(" ")
        verb, arg = verb.lower(), arg.strip()
        if verb == "help":
            ctx.ui.info(ctx.help_text)
            continue
        ctx.spend()
        if verb == "scan":
            found = True
            ctx.ui.say(f"  host found: {SHELL_HOST}", "accent")
        elif verb == "connect":
            if not found:
                ctx.ui.warn("No known hosts. Try 'scan' first.")
            elif arg.lower() != SHELL_HOST:
                ctx.ui.warn(f"Unknown host '{arg}'. Known: {SHELL_HOST}")
            else:
                connected = True
                ctx.ui.ok(f"Connected to {SHELL_HOST}.")
        elif verb == "ls":
            ctx.ui.say("  " + "  ".join(SHELL_FILES) if connected else "  (not connected)")
        elif verb == "cat":
            if not connected:
                ctx.ui.warn("Connect to a host first.")
            elif arg not in SHELL_FILES:
                ctx.ui.warn(f"No such file: {arg}")
            else:
                ctx.ui.say("  " + SHELL_FILES[arg], "accent")
                if arg == "welcome.txt":
                    ctx.ui.ok("Orientation complete.")
                    return
        else:
            ctx.ui.warn("Unknown command. Type 'help'.")


STAGES: dict[str, Callable[[MissionContext, dict[str, Any]], None]] = {
    "shell": play_shell, "firewall": play_firewall, "cipher": play_cipher,
    "password": play_password, "network": play_network, "escape": play_escape,
}


def run_stages(ctx: MissionContext, stages: list[dict[str, Any]], start: int = 0,
               between: Callable[[MissionContext, int], None] | None = None) -> None:
    """Play stages from ``start``, cooling detection between them. Raises MissionFailed.

    ``between(ctx, n)`` runs after stage ``n`` (0-based) when another stage follows;
    the game uses it to checkpoint and offer the pause menu.
    """
    for n, stage in enumerate(stages):
        if n < start:
            continue
        player = STAGES.get(stage["type"])
        if player is None:
            raise ValueError(f"unsupported stage type {stage['type']!r}")
        ctx.ui.rule()
        ctx.ui.say(f"STAGE {n + 1}/{len(stages)}: {stage.get('label', stage['type'].upper())}", "accent")
        params = stage.get("params", {})
        ctx.patrol_rate = float(params.get("patrol", 0))
        if ctx.patrol_rate:
            ctx.ui.warn("Security patrol active: detection climbs with every tick.")
        player(ctx, params)
        ctx.solved[stage["type"]] = ctx.solved.get(stage["type"], 0) + 1
        ctx.patrol_rate = 0.0
        ctx.puzzle, ctx.stage_kind = None, ""
        if n < len(stages) - 1:
            ctx.cooldown()
            if between is not None:
                between(ctx, n)


# -- missions ----------------------------------------------------------------------
@dataclass
class Mission:
    """One campaign mission, defined as data (see missions/mission_data.py)."""

    mid: int
    title: str
    tier: str
    intro: str
    briefing: str
    primary: list[str]
    optional: list[dict[str, Any]]
    stages: list[dict[str, Any]]
    par_ticks: int
    grace_ticks: int
    max_ticks: int
    reward_xp: int
    reward_credits: int
    completion: str
    failure: list[str] = field(default_factory=lambda: [
        "Detection reaches 100%", "Tick budget runs out", "A lock runs out of attempts"])
    events: bool = True


@dataclass
class MissionResult:
    """Outcome of one mission run."""

    success: bool
    reason: str
    ticks: float
    peak: float
    wrong: int
    optional_done: list[str]
    solved: dict[str, int]
    items_used: list[str]
    bonus_credits: int
    aborted: bool = False

    @property
    def ghost(self) -> bool:
        """Won with zero detection."""
        return self.success and self.peak == 0


def evaluate_optionals(mission: Mission, ctx: MissionContext) -> list[str]:
    """Ids of optional objectives met by this run."""
    done = []
    for o in mission.optional:
        kind, value = o["kind"], o["value"]
        met = ((kind == "max_ticks" and ctx.ticks <= value)
               or (kind == "max_detection" and ctx.meter.peak < value)
               or (kind == "hidden_node" and ctx.found_hidden)
               or (kind == "no_wrong" and ctx.wrong_guesses <= value))
        if met:
            done.append(o["id"])
    return done


def run_mission(ui: UI, rng: GameRNG, cfg: dict[str, Any], mission: Mission, difficulty: str = "normal",
                inventory: Inventory | None = None, checkpoint: dict[str, Any] | None = None,
                between: Callable[[MissionContext, int], None] | None = None) -> MissionResult:
    """Play a whole mission (optionally resuming a checkpoint) and return the result."""
    ctx = MissionContext(ui, rng, cfg, difficulty, mission.grace_ticks, mission.max_ticks,
                         inventory=inventory, events=mission.events)
    start = 0
    if checkpoint:
        start = int(checkpoint.get("stage", 0))
        ctx.ticks = float(checkpoint.get("ticks", 0.0))
        ctx.meter.level = ctx.meter.peak = float(checkpoint.get("detection", 0.0))
        ctx.meter.peak = max(ctx.meter.peak, float(checkpoint.get("peak", 0.0)))
        ctx.wrong_guesses = int(checkpoint.get("wrong", 0))
    reason, success, aborted = "", True, False
    try:
        run_stages(ctx, mission.stages, start, between)
    except MissionFailed as exc:
        success, reason = False, exc.reason
    except MissionAborted:
        success, reason, aborted = False, "Mission aborted by operator.", True
    return MissionResult(success, reason, ctx.ticks, ctx.meter.peak, ctx.wrong_guesses,
                         evaluate_optionals(mission, ctx) if success else [], dict(ctx.solved),
                         list(ctx.items_used), ctx.bonus_credits if success else 0, aborted)
