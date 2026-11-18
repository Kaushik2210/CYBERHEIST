"""Random events: seeding, effects, fairness caps and Signal Mask."""
import copy

from cyberheist.challenges import encryption
from cyberheist.core.rng import GameRNG
from cyberheist.core.state import load_config
from cyberheist.interface.theme import Theme
from cyberheist.interface.ui import UI, ScriptedIO
from cyberheist.missions.mission_runner import MissionContext, run_stages
from cyberheist.systems.inventory import Inventory
from cyberheist.systems.random_events import EVENT_ORDER, EventEngine

CFG = load_config()


def make(inputs=(), seed=1, events=True, cfg=CFG, **kw):
    io = ScriptedIO(inputs, autopilot=kw.pop("autopilot", False))
    ctx = MissionContext(UI(io, Theme(color=False, unicode=False), animations=False),
                         GameRNG(seed), cfg, events=events, **kw)
    return ctx, io


def test_events_are_seeded_and_reproducible():
    runs = []
    for _ in range(2):
        ctx, _ = make(seed=42, max_ticks=10_000, grace_ticks=10_000)
        ctx.spend("command", 500)
        runs.append(list(ctx.events.fired))
    assert runs[0] == runs[1] and runs[0]


def test_at_most_one_event_per_block():
    cfg = copy.deepcopy(CFG)
    cfg["events"]["probabilities"] = {k: 1.0 for k in EVENT_ORDER}
    ctx, _ = make(cfg=cfg, max_ticks=1000, grace_ticks=1000)
    ctx.spend("command", 35)
    assert ctx.events.fired == ["firewall_update"] * 3


def test_patrol_adds_alarm_and_signal_mask_blocks_it():
    ctx, io = make()
    ctx.events.fire(ctx, "security_patrol")
    assert ctx.meter.level == 15
    inv = Inventory(CFG["items"], 2)
    inv.add("signal_mask")
    inv.equip("signal_mask")
    masked, io2 = make(inventory=inv)
    masked.events.fire(masked, "security_patrol")
    assert masked.meter.level == 0 and "absorbed" in io2.text()
    masked.events.fire(masked, "security_patrol")
    assert masked.meter.level == 15


def test_patrol_never_pushes_past_event_ceiling():
    ctx, _ = make()
    ctx.meter.level = 75
    ctx.events.fire(ctx, "security_patrol")
    assert ctx.meter.level == 80 and not ctx.meter.failed
    ctx.meter.level = 90
    ctx.events.fire(ctx, "security_patrol")
    assert ctx.meter.level == 90


def test_firewall_update_never_exhausts_tick_budget():
    ctx, _ = make(max_ticks=20)
    ctx.ticks = 18
    ctx.events.fire(ctx, "firewall_update")
    assert ctx.ticks == 19
    ctx.check()


def test_bonus_events():
    ctx, io = make()
    for eid in ("encrypted_backup", "hidden_intel", "exposed_vulnerability", "suspicious_traffic",
                "anonymous_message"):
        ctx.events.fire(ctx, eid)
    assert ctx.bonus_credits == CFG["events"]["backup_credits"]
    assert ctx.free_reveals == 1 and ctx.free_hints == 1 and "ANON:" in io.text()
    assert ctx.meter.level == 0


def test_free_hint_and_banked_intel_are_spent_in_cipher_stage():
    seed = 9
    p = encryption.generate(GameRNG(seed).fork("cipher-hex"), "hex", 3, tough=True)  # Normal = tough
    ctx, io = make(["use intel", "hint", p.answer], seed=seed, events=False)
    ctx.free_hints, ctx.free_reveals = 1, 1
    run_stages(ctx, [{"type": "cipher", "params": {"kind": "hex"}}])
    assert ctx.free_hints == 0 and ctx.free_reveals == 0 and ctx.ticks == 1
    assert "Intel: Plaintext begins" in io.text() and "Free hint" in io.text()


def test_intel_without_bank_is_refused():
    ctx, io = make(events=False)
    assert not ctx.use_item("intel") and "No banked intel" in io.text()


def test_autopilot_still_wins_with_events_on():
    stages = [{"type": "network", "params": {"hidden": 1}},
              {"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8}},
              {"type": "cipher", "params": {"kind": "vigenere"}},
              {"type": "password", "params": {}},
              {"type": "escape", "params": {"rounds": 3}}]
    for seed in range(50):
        ctx, _ = make(seed=seed, autopilot=True, grace_ticks=200, max_ticks=500)
        run_stages(ctx, stages)
