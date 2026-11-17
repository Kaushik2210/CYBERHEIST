"""Mission runner: stage loops, clock, detection and failure conditions."""
import pytest

from challenges import firewall
from core.rng import GameRNG
from core.state import MissionFailed, load_config
from interface.theme import Theme
from interface.ui import UI, ScriptedIO
from missions.mission_runner import MissionContext, run_stages

CFG = load_config()
ALL_STAGES = [
    {"type": "network", "params": {"hidden": 1}},
    {"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8}},
    {"type": "cipher", "params": {"kind": "caesar"}},
    {"type": "password", "params": {}},
    {"type": "escape", "params": {"rounds": 3}},
]


def make_ctx(io, seed=1, **kw):
    ui = UI(io, Theme(color=False, unicode=False), animations=False)
    return MissionContext(ui, GameRNG(seed), CFG, **kw)


def test_autopilot_clears_every_stage_type():
    for seed in range(50):
        ctx = make_ctx(ScriptedIO(autopilot=True), seed, grace_ticks=200, max_ticks=500)
        run_stages(ctx, ALL_STAGES)
        assert not ctx.meter.failed


@pytest.mark.parametrize("kind", ["caesar", "vigenere", "substitution", "binary", "hex", "pattern"])
def test_autopilot_clears_each_cipher(kind):
    ctx = make_ctx(ScriptedIO(autopilot=True), 3)
    run_stages(ctx, [{"type": "cipher", "params": {"kind": kind}}])


def test_bad_input_never_crashes_and_shared_commands_work():
    seed = 5
    p = firewall.generate(GameRNG(seed).fork("firewall"), 6, 4, 8)
    answer = " ".join(str(i + 1) for i in p.secret)
    io = ScriptedIO(["x", "1 1 1 1", "99 1 2 3", "?", "status", "b", "", answer])
    ctx = make_ctx(io, seed)
    run_stages(ctx, [{"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8}}])
    out = io.text()
    assert "Enter exactly 4" in out and "only once" in out and "DET" in out and "No going back" in out
    assert ctx.wrong_guesses == 0


def test_wrong_guesses_fail_mission_at_100():
    io = ScriptedIO(["nope"] * 20)
    ctx = make_ctx(io, grace_ticks=500, max_ticks=500)
    with pytest.raises(MissionFailed, match="Detection"):
        run_stages(ctx, [{"type": "cipher", "params": {"kind": "hex", "attempts": 30}}])
    assert ctx.wrong_guesses == 13


def test_tick_budget_failure():
    io = ScriptedIO(["scan"] * 50)
    ctx = make_ctx(io, max_ticks=6)
    with pytest.raises(MissionFailed, match="Tick budget"):
        run_stages(ctx, [{"type": "network", "params": {}}])


def test_overtime_past_grace_adds_detection():
    ctx = make_ctx(ScriptedIO(), grace_ticks=5, max_ticks=100)
    ctx.spend("command", 5)
    assert ctx.meter.level == 0
    ctx.spend("command", 3)
    assert ctx.meter.level == 3


def test_lab_tools_cost_detection_in_tough_mode_only():
    from challenges import encryption
    seed = 4
    for difficulty, expected in (("normal", 2.0), ("easy", 0.0)):
        tough = difficulty != "easy"
        p = encryption.generate(GameRNG(seed).fork("cipher-caesar"), "caesar", 3, tough=tough)
        io = ScriptedIO([f"shift {p.shift}", p.answer])
        ctx = make_ctx(io, seed, difficulty=difficulty)
        run_stages(ctx, [{"type": "cipher", "params": {"kind": "caesar"}}])
        assert ctx.meter.peak == expected * ctx.diff["detection_mult"]


def test_layered_stage_with_unhex_and_shift():
    from challenges import encryption
    seed = 6
    p = encryption.generate(GameRNG(seed).fork("cipher-layered"), "layered", 3, tough=True)
    io = ScriptedIO(["unhex", f"shift {p.shift}", p.answer])
    ctx = make_ctx(io, seed)
    run_stages(ctx, [{"type": "cipher", "params": {"kind": "layered"}}])
    assert "Hex layer removed" in io.text() and ctx.meter.peak == 4


def test_firewall_tightness_follows_difficulty():
    for difficulty, margin, repeats in (("easy", None, False), ("normal", 2, False), ("hard", 1, True)):
        io = ScriptedIO(autopilot=True)
        ctx = make_ctx(io, 9, difficulty=difficulty, grace_ticks=300, max_ticks=600)
        run_stages(ctx, [{"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8}}])
        p = firewall.generate(GameRNG(9).fork("firewall"), 6, 4 + ctx.diff["code_length_delta"],
                              8 + ctx.diff["attempt_bonus"], repeats=repeats, margin=margin)
        out = io.text()
        assert f"{p.attempts} attempts" in out and f"Solver par: {p.par}" in out
        assert ("MAY REPEAT" in out) == repeats


def test_neural_accelerator_cuts_tick_costs():
    ctx = make_ctx(ScriptedIO(), neural=True)
    ctx.spend("scan")
    assert abs(ctx.ticks - 2 * 0.8) < 1e-9
