"""Run debrief: what each stage cost, how it compared with the solver, and one tip."""
from challenges import firewall
from core.rng import GameRNG
from core.state import load_config
from interface.theme import Theme
from interface.ui import UI, ScriptedIO, visible_len
from missions.mission_runner import Mission, run_mission
from systems.debrief import ChainLog, StageLog, biggest_leak, summarize

CFG = load_config()
DET = CFG["detection"]


def mission(stages, **kw):
    base = dict(mid=1, title="Debrief Test", tier="Test", intro="", briefing="", primary=["x"], optional=[],
                stages=stages, par_ticks=10, grace_ticks=200, max_ticks=400, reward_xp=0,
                reward_credits=0, completion="", events=False)
    base.update(kw)
    return Mission(**base)


def play(stages, inputs=(), autopilot=False, seed=11, debrief=True, difficulty="normal"):
    io = ScriptedIO(list(inputs), autopilot=autopilot)
    ui = UI(io, Theme(color=False, unicode=True), animations=False)
    r = run_mission(ui, GameRNG(seed), CFG, mission(stages), difficulty, debrief=debrief)
    return r, io


# -- pure summaries -------------------------------------------------------------------
def test_careless_probe_names_the_probe_it_contradicted():
    log = StageLog("firewall", "Gate", cleared=True,
                   chains=[ChainLog("Firewall", par=4, used=6, solved=True, careless=[(3, 1), (5, 4)])])
    facts, tips = summarize(log, DET)
    assert "Firewall: 6 probes, solver par 4 (+2)" in facts
    assert tips[0].startswith("Firewall: probe 3 contradicted the feedback from probe 1")
    assert "2 careless probes" in " ".join(facts)


def test_careful_but_slow_and_faster_than_solver():
    slow = StageLog("password", "Admin", cleared=True,
                    chains=[ChainLog("Passphrase", par=3, used=5, solved=True, noun="guess")])
    facts, tips = summarize(slow, DET)
    assert "Passphrase: 5 guesses, solver par 3 (+2)" in facts
    assert "every guess fit the clues" in tips[0] and "characters" in tips[0]
    fast = StageLog("firewall", "Gate", cleared=True, chains=[ChainLog("Firewall", par=5, used=3, solved=True)])
    facts, tips = summarize(fast, DET)
    assert "Firewall: 3 probes, solver par 5 (beat it by 2)" in facts and tips == []


def test_locked_out_chain_is_reported():
    log = StageLog("firewall", "Gate", chains=[ChainLog("Firewall", par=4, used=5, solved=False)])
    facts, _ = summarize(log, DET)
    assert any("locked out after 5 probes" in f for f in facts)


def test_cipher_tips_price_wrong_decodes_against_lab_tools():
    log = StageLog("cipher", "Intercept", cleared=True, wrong=2, hints=1, tools=0, tough=True)
    facts, tips = summarize(log, DET)
    assert "2 wrong decodes" in " ".join(facts) and "1 hint" in " ".join(facts)
    assert f"+{DET['wrong_guess']} detection" in tips[0] and f"+{DET['lab_tool']}" in tips[0]


def test_network_tip_points_at_the_safer_locked_route():
    log = StageLog("network", "Grid", cleared=True, scans=3, scans_needed=3,
                   route={"label": "INET > FW > GW > SRV-B > BKP", "rating": "HIGH", "added": 14,
                          "best_label": "INET > FW > GW > SRV-A* > DB", "best_rating": "LOW",
                          "best_locked": True})
    facts, tips = summarize(log, DET)
    assert "route HIGH risk (+14 detection)" in " ".join(facts)
    assert "LOW" in tips[0] and "locked" in tips[0]


def test_network_tip_for_stopping_scans_early():
    log = StageLog("network", "Grid", cleared=True, scans=1, scans_needed=3,
                   route={"label": "a", "rating": "LOW", "added": 0, "best_label": "a", "best_rating": "LOW",
                          "best_locked": False})
    _, tips = summarize(log, DET)
    assert "1 of 3" in tips[0]


def test_escape_tips_match_the_round_kind_missed():
    for kind, word in (("memory", "chunks"), ("sequence", "initials"), ("clue", "rule")):
        _, tips = summarize(StageLog("escape", "Out", cleared=True, rounds=3, misses=[kind]), DET)
        assert word in tips[0], (kind, tips)


def test_biggest_leak_picks_the_costliest_stage():
    logs = [StageLog("network", "A", detection=4), StageLog("cipher", "B", detection=21),
            StageLog("escape", "C", detection=-3)]
    assert biggest_leak(logs).label == "B"
    assert biggest_leak([StageLog("shell", "A", detection=0)]) is None


# -- in a real run --------------------------------------------------------------------
def test_firewall_run_debrief_catches_a_repeated_wrong_probe():
    stage = {"type": "firewall", "label": "Gate", "params": {"pool": 6, "length": 4, "margin": 4}}
    p = firewall.generate(GameRNG(11).fork("firewall"), 6, 4, 8, margin=4)
    wrong = next(c for c in firewall.candidates(6, 4, False) if c != p.secret)
    as_text = " ".join(str(i + 1) for i in wrong)
    answer = " ".join(str(i + 1) for i in p.secret)
    r, io = play([stage], [as_text, as_text, answer])
    text = io.text()
    assert r.success and "DEBRIEF" in text
    assert "probe 2 contradicted the feedback from probe 1" in text
    log = r.stages[0]
    assert log.cleared and log.wrong == 2 and log.chains[0].careless == [(2, 1)]
    assert log.detection > 0 and log.ticks > 0
    assert max(visible_len(line) for line in io.output) <= 80


def test_autopilot_daily_style_run_has_a_summary_that_fits_80_columns():
    stages = [{"type": "network", "label": "Grid", "params": {"hidden": 2}},
              {"type": "firewall", "label": "Gate"}, {"type": "cipher", "label": "Intercept",
                                                       "params": {"kind": "vigenere"}},
              {"type": "password", "label": "Admin"}, {"type": "escape", "label": "Out"}]
    r, io = play(stages, autopilot=True, difficulty="hard")
    text = io.text()
    assert r.success and text.count("DEBRIEF") == 5 and "RUN SUMMARY" in text
    assert [s.kind for s in r.stages] == ["network", "firewall", "cipher", "password", "escape"]
    assert max(visible_len(line) for line in io.output) <= 80


def test_failed_stage_still_gets_a_debrief():
    stage = {"type": "cipher", "label": "Intercept", "params": {"kind": "hex", "attempts": 1}}
    r, io = play([stage], ["nope", "still nope", "no", "no", "no"], difficulty="easy")
    assert not r.success and "DEBRIEF" in io.text()
    assert r.stages[0].cleared is False and r.stages[0].wrong >= 1


def test_debrief_off_prints_nothing_but_still_records():
    r, io = play([{"type": "shell"}, {"type": "escape"}], autopilot=True, debrief=False)
    assert r.success and "DEBRIEF" not in io.text() and "RUN SUMMARY" not in io.text()
    assert len(r.stages) == 2 and r.stages[0].commands >= 3
