"""Daily challenge, best scores per seed, and adaptive difficulty."""
import datetime as dt

from core.game import Game
from database.database import SaveManager
from interface.ui import ScriptedIO
from missions.mission_runner import MissionResult
from systems import adaptive
from systems.daily import DAILY_VERSION, build_daily, daily_seed, run_seed, score_run
from systems.statistics import Statistics

DAY = dt.date(2026, 11, 18)


def result(success=True, ticks=50, peak=20, wrong=2):
    return MissionResult(success, "" if success else "caught", ticks, peak, wrong, [], {}, [], 0)


def test_daily_seed_and_run_are_the_same_all_day():
    assert daily_seed(DAY) == 20261118
    assert build_daily(DAY).stages == build_daily(DAY).stages
    assert build_daily(DAY).stages != build_daily(DAY + dt.timedelta(days=1)).stages
    kinds = [s["type"] for s in build_daily(DAY).stages]
    assert kinds == ["network", "firewall", "cipher", "password", "escape"]


def test_run_seed_includes_the_puzzle_version():
    assert run_seed(DAY) == 20261118 * 100 + DAILY_VERSION
    assert run_seed(DAY) != run_seed(DAY + dt.timedelta(days=1))


# Fingerprint of the daily run for DAY on Normal: a hash of every answer the autopilot
# types. It only changes when the puzzles themselves change, not when UI text does.
DAILY_FINGERPRINT = {1: "ebe89426ab50add7"}


def test_daily_puzzles_unchanged_for_this_version():
    import hashlib

    from core.rng import GameRNG
    from core.state import load_config
    from interface.theme import Theme
    from interface.ui import UI
    from missions.mission_runner import run_mission
    io = ScriptedIO(autopilot=True)
    run_mission(UI(io, Theme(color=False), animations=False), GameRNG(run_seed(DAY)), load_config(),
                build_daily(DAY), "normal")
    answers = [line for line in io.output if line.startswith("<") and line.endswith(">")]
    fingerprint = hashlib.sha256("\n".join(answers).encode()).hexdigest()[:16]
    assert fingerprint == DAILY_FINGERPRINT.get(DAILY_VERSION), (
        "The daily puzzles changed. Bump DAILY_VERSION in systems/daily.py so old and new "
        f"scores aren't mixed, then record the new fingerprint here: {DAILY_VERSION + 1}: '{fingerprint}'")


def test_score_formula():
    s = score_run(result(ticks=80, peak=20, wrong=2), par_ticks=70)
    assert s.total == 1000 - 5 * 10 - 4 * 20 - 30 * 2
    under = score_run(result(ticks=60, peak=0, wrong=0), par_ticks=70)
    assert under.total == 1000 + 200 + 300
    assert score_run(result(success=False), 70).total == 0
    assert score_run(result(ticks=500, peak=100, wrong=40), 70).total == 0       # never negative


def test_best_score_is_kept_per_seed(tmp_path):
    sm = SaveManager(tmp_path / "s.db")
    sm.open()
    assert sm.record_score("daily-normal", 1, 500, 60, 10, "d") == (500, True)
    assert sm.record_score("daily-normal", 1, 300, 70, 20, "d") == (500, False)
    assert sm.record_score("daily-normal", 1, 800, 50, 5, "d") == (800, True)
    assert sm.record_score("daily-hard", 1, 100, 50, 5, "d") == (100, True)      # separate board per difficulty
    rows = sm.load_scores("daily-normal")
    assert len(rows) == 1 and rows[0]["best"] == 800 and rows[0]["plays"] == 3
    sm.close()


def test_adaptive_steps_down_after_failures_and_up_after_clean_wins():
    s = Statistics()
    assert adaptive.suggest("normal", s) is None
    for _ in range(2):
        s.record_mission(1, False, 10, 20, 100, 3, {}, 0)
    assert adaptive.suggest("normal", s) == "easy"
    assert adaptive.suggest("easy", s) is None                                    # already the floor
    for _ in range(3):
        s.record_mission(1, True, 10, 20, 30, 0, {}, 0)
    assert s["fail_streak"] == 0 and s["clean_streak"] == 3
    assert adaptive.suggest("normal", s) == "hard"
    assert adaptive.suggest("hard", s) is None                                    # already the ceiling
    s.record_mission(1, True, 10, 20, 70, 0, {}, 0)                               # a messy win resets it
    assert s["clean_streak"] == 0


def run_game(tmp_path, inputs, day=DAY):
    io = ScriptedIO(inputs, autopilot=True)
    g = Game(io, tmp_path / "save.db", seed=3, missions=[], today=lambda: day)
    g.run()
    return g, io


def test_daily_challenge_end_to_end_keeps_best(tmp_path):
    g, io = run_game(tmp_path, ["Neo_01", "3", "d", "8"])
    out = io.text()
    assert "DAILY CHALLENGE 2026-11-18" in out and "MISSION 00" not in out
    assert f"Seed 20261118{DAILY_VERSION:02d}" in out and "DAILY SCORE" in out and "NEW PERSONAL BEST" in out
    assert g.stats["daily_runs"] == 1
    first = g.stats["daily_best"]
    g2, io2 = run_game(tmp_path, ["3", "d", "8"])
    out2 = io2.text()
    assert "2026-11-18 (today)" in out2                                           # the board shows today's best
    # Same day, same seed, same autopilot: an identical run, so the best score stands.
    assert f"Today's best stays at {first:,}" in out2 and "NEW PERSONAL BEST" not in out2
    assert g2.stats["daily_runs"] == 2
    sm = SaveManager(tmp_path / "save.db")
    sm.open()
    row = sm.load_scores(f"daily-v{DAILY_VERSION}-normal")[0]
    assert row["seed"] == 20261118 and row["plays"] == 2 and row["best"] == first
    sm.close()


def test_difficulty_balance_guard():
    """A logic-perfect autopilot should clear every Easy/Normal daily and most Hard ones.

    Measured at 15/15, 15/15 and 11/15 over these dates; the thresholds catch regressions
    like the one that dropped Hard to 7/30 before careful probes existed.
    """
    from core.rng import GameRNG
    from core.state import load_config
    from interface.theme import Theme
    from interface.ui import UI
    from missions.mission_runner import run_mission
    cfg = load_config()
    wins = {}
    for diff in ("easy", "normal", "hard"):
        wins[diff] = 0
        for k in range(15):
            day = dt.date(2026, 11, 1) + dt.timedelta(days=k)
            r = run_mission(UI(ScriptedIO(autopilot=True), Theme(color=False), animations=False),
                            GameRNG(run_seed(day)), cfg, build_daily(day), diff)
            wins[diff] += r.success
    assert wins["easy"] == 15 and wins["normal"] == 15 and wins["hard"] >= 10, wins


def test_adaptive_setting_changes_difficulty_in_game(tmp_path):
    g, io = run_game(tmp_path, ["Neo_01", "7", "7", "b", "8"])                    # turn adaptive on
    assert g.settings.get("adaptive") is True
    g.stats.values["fail_streak"] = 2
    g.ui = g._build_ui()
    g.save.open()
    g._adapt()
    assert g.settings.get("difficulty") == "easy" and g.stats["fail_streak"] == 0
    assert "stepping down to EASY" in io.text()
    g.save.close()
