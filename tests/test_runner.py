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


def test_network_scans_cost_detection_in_tough_mode_only():
    from challenges import network
    for difficulty in ("easy", "normal"):
        m = network.generate(GameRNG(2).fork("network"), "DATABASE", 1, 0 if difficulty == "easy" else 1)
        open_route = next(i for i, r in enumerate(_mapped_routes(m), 1) if not r.locked)
        io = ScriptedIO(["scan"] * 5 + ["routes", f"route {open_route}"])
        ctx = make_ctx(io, 2, difficulty=difficulty, grace_ticks=300, max_ticks=600)
        run_stages(ctx, [{"type": "network", "params": {"hidden": 1}}])
        scans = 0 if difficulty == "easy" else 4 * 3 + 1 * 6   # four layers, then a double-cost deep scan
        route = network.route_detection(_mapped_routes(m)[open_route - 1].rating,
                                        GameRNG(2).fork("route"), CFG["detection"])
        assert ctx.meter.peak == pytest.approx((scans + route) * ctx.diff["detection_mult"])
        assert "IS LOCKED" not in io.text()   # the open route needs no cracking


def _mapped_routes(m):
    from challenges import network
    full = network.NetworkMap(dict(m.edges), set(m.hidden), m.target, set(m.nodes), locked=set(m.locked))
    return full.routes()


def test_locked_route_requires_cracking_the_node():
    from challenges import network
    seed = 5
    m = network.generate(GameRNG(seed).fork("network"), "DATABASE", 1, 1)
    node = sorted(_mapped_routes(m)[0].locked)[0]
    lock = firewall.generate(GameRNG(seed).fork(f"lock-{node}"), 6, 3, 0, margin=2)
    answer = " ".join(str(i + 1) for i in lock.secret)
    io = ScriptedIO(["scan"] * 5 + ["route 1", answer])
    ctx = make_ctx(io, seed, grace_ticks=300, max_ticks=600)
    run_stages(ctx, [{"type": "network", "params": {"hidden": 1}}])
    out = io.text()
    assert f"{node} IS LOCKED" in out and f"{node} chain accepted in 1 probe" in out and "Routed via" in out


def test_failing_a_node_lock_fails_the_mission():
    from challenges import network
    seed = 5
    m = network.generate(GameRNG(seed).fork("network"), "DATABASE", 1, 1)
    node = sorted(_mapped_routes(m)[0].locked)[0]
    lock = firewall.generate(GameRNG(seed).fork(f"lock-{node}"), 6, 3, 0, margin=2)
    wrong = "1 2 3" if lock.secret != (0, 1, 2) else "4 5 6"
    io = ScriptedIO(["scan"] * 5 + ["route 1"] + [wrong] * 20)
    ctx = make_ctx(io, seed, grace_ticks=300, max_ticks=600)
    with pytest.raises(MissionFailed, match=f"{node} locked out"):
        run_stages(ctx, [{"type": "network", "params": {"hidden": 1}}])


def test_password_toughness_follows_difficulty():
    for difficulty in ("easy", "normal", "hard"):
        io = ScriptedIO(autopilot=True)
        ctx = make_ctx(io, 3, difficulty=difficulty, grace_ticks=300, max_ticks=600)
        run_stages(ctx, [{"type": "password", "params": {}}])
        out = io.text()
        assert ("add up to" in out) == (difficulty != "easy")
        assert ("list not recovered" in out) == (difficulty == "hard")
        assert ("Base word is one of" in out) == (difficulty != "hard")
        assert "Solver par:" in out


def test_memory_rounds_clear_the_screen_before_asking():
    from challenges import escape
    seed = 3
    seq = escape.generate(GameRNG(seed).fork("escape"), 4, 4, tough=True)
    inputs = []
    for r in seq.rounds:
        if r.memorize:
            inputs.append("")              # ENTER once memorised
        inputs.append(r.answer)
    io = ScriptedIO(inputs)
    ctx = make_ctx(io, seed)
    run_stages(ctx, [{"type": "escape", "params": {"rounds": 4}}])
    out = io.output
    for r in seq.rounds:
        if r.memorize:
            shown = next(i for i, line in enumerate(out) if r.memorize in line)
            cleared = out.index("<screen cleared>", shown)
            asked = next(i for i, line in enumerate(out) if i > cleared and r.prompt in line)
            assert shown < cleared < asked
    assert "Clean exit." in io.text()


def test_escape_toughness_follows_difficulty():
    for difficulty, kinds in (("easy", {"choice", "code"}), ("normal", {"memory", "sequence", "clue"})):
        io = ScriptedIO(autopilot=True)
        ctx = make_ctx(io, 8, difficulty=difficulty)
        run_stages(ctx, [{"type": "escape", "params": {"rounds": 6}}])
        from challenges import escape
        seq = escape.generate(GameRNG(8).fork("escape"), 6, 4 + max(0, ctx.diff["attempt_bonus"]),
                              tough=difficulty != "easy")
        assert {r.kind for r in seq.rounds} <= kinds
        assert ("<screen cleared>" in io.output) == any(r.memorize for r in seq.rounds)


def test_careful_firewall_probes_cost_half_detection():
    seed = 5
    p = firewall.generate(GameRNG(seed).fork("firewall"), 6, 4, 8, margin=2)
    answer = " ".join(str(i + 1) for i in p.secret)
    first = next(" ".join(map(str, g)) for g in ((1, 2, 3, 4), (2, 3, 4, 5)) if " ".join(map(str, g)) != answer)
    # Probe 1 is careful (no clues yet). Repeating it contradicts its own feedback: careless.
    io = ScriptedIO([first, first, answer])
    ctx = make_ctx(io, seed, grace_ticks=300, max_ticks=600)
    run_stages(ctx, [{"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8}}])
    wrong = CFG["detection"]["wrong_guess"]
    assert ctx.meter.peak == wrong * CFG["detection"]["careful_probe"] + wrong
    out = io.text()
    assert "careful probe" in out and "careless probe" in out


def test_careful_password_guesses_cost_half_detection():
    from challenges import password
    seed = 7
    p = password.generate(GameRNG(seed).fork("password"), 8, 2, 4, 5, 6, sum_clue=True, margin=2)
    wrong_guess = "".join({"W": "A", "D": "0", "S": p.symbols[0]}[m] for m in p.mask)
    assert wrong_guess != p.secret
    io = ScriptedIO([wrong_guess, wrong_guess, p.secret])
    ctx = make_ctx(io, seed, grace_ticks=300, max_ticks=600)
    run_stages(ctx, [{"type": "password", "params": {}}])
    wrong = CFG["detection"]["wrong_guess"]
    assert ctx.meter.peak == wrong * CFG["detection"]["careful_probe"] + wrong


def test_neural_accelerator_cuts_tick_costs():
    ctx = make_ctx(ScriptedIO(), neural=True)
    ctx.spend("scan")
    assert abs(ctx.ticks - 2 * 0.8) < 1e-9
