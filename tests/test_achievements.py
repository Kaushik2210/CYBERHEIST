"""Statistics counters and achievement unlocks."""
from core.rng import GameRNG
from core.state import load_config
from interface.theme import Theme
from interface.ui import UI, ScriptedIO
from missions.mission_runner import MissionContext, run_stages
from systems.achievements import ACHIEVEMENTS, AchievementTracker, notify
from systems.statistics import Statistics

CFG = load_config()


def win(stats, mid=1, ticks=20, par=10, peak=30, solved=None):
    stats.record_mission(mid, True, ticks, par, peak, 0, solved or {}, 0, 500)


def test_spec_achievements_exist():
    assert [a.name for a in ACHIEVEMENTS] == [
        "First Breach", "Ghost Mode", "Cipher Master", "Speed Demon",
        "Digital Phantom", "Black Market Regular", "Zero Day Legend"]


def test_record_mission_counters():
    s = Statistics()
    win(s, solved={"cipher": 2, "firewall": 1})
    s.record_mission(2, False, 50, 30, 100, 7, {"network": 1}, 2)
    assert s["missions_attempted"] == 2 and s["missions_won"] == 1 and s["missions_failed"] == 1
    assert s["ciphers_solved"] == 2 and s["firewalls_cracked"] == 1 and s["networks_mapped"] == 1
    assert s["wrong_guesses"] == 7 and s["items_used"] == 2 and s["highest_detection"] == 100
    assert s["streak"] == 0 and s["best_streak"] == 1 and s["credits_earned"] == 500


def test_each_achievement_unlocks_once():
    s, t = Statistics(), AchievementTracker()
    assert t.evaluate(s) == []
    win(s)
    assert [a.aid for a in t.evaluate(s)] == ["first_breach"]
    assert t.evaluate(s) == []
    win(s, peak=0)
    assert [a.aid for a in t.evaluate(s)] == ["ghost_mode"]
    win(s, ticks=9, par=10)
    assert [a.aid for a in t.evaluate(s)] == ["speed_demon"]
    win(s, solved={"cipher": 10})
    assert [a.aid for a in t.evaluate(s)] == ["cipher_master"]
    win(s)
    assert [a.aid for a in t.evaluate(s)] == ["digital_phantom"]
    s.bump("items_bought", 5)
    assert [a.aid for a in t.evaluate(s)] == ["market_regular"]
    win(s, mid=10)
    assert [a.aid for a in t.evaluate(s)] == ["zero_day_legend"]
    assert len(t.unlocked) == 7


def test_ties_and_failures_do_not_count():
    s, t = Statistics(), AchievementTracker()
    win(s, ticks=10, par=10)                       # matching par is not beating it
    s.record_mission(3, False, 5, 10, 0, 0, {}, 0)  # a failed run with zero detection
    t.evaluate(s)
    assert s["speed_runs"] == 0 and s["ghost_runs"] == 0
    assert "speed_demon" not in t.unlocked and "ghost_mode" not in t.unlocked

    s2, t2 = Statistics(), AchievementTracker()
    for _ in range(4):
        win(s2)
    s2.record_mission(5, False, 5, 10, 50, 0, {}, 0)  # breaks the streak
    win(s2)
    t2.evaluate(s2)
    assert s2["best_streak"] == 4 and s2["streak"] == 1
    assert "digital_phantom" not in t2.unlocked


def test_progress_rows_and_notification():
    s, t = Statistics(), AchievementTracker()
    win(s, solved={"cipher": 3})
    t.evaluate(s)
    rows = {r[1]: r for r in t.rows(s)}
    assert rows["First Breach"][0] == "UNLOCKED" and rows["Cipher Master"][2] == "3/10"
    io = ScriptedIO()
    ui = UI(io, Theme(color=False, unicode=False), animations=False, sound=True)
    notify(ui, [ACHIEVEMENTS[0]])
    assert "ACHIEVEMENT UNLOCKED" in io.text() and "First Breach" in io.text() and io.bells == 1


def test_save_rows_round_trip():
    s, t = Statistics(), AchievementTracker()
    win(s)
    t.evaluate(s)
    assert Statistics(s.to_rows()).to_rows() == s.to_rows()
    assert AchievementTracker(t.to_rows()).unlocked == t.unlocked
    assert "bogus" not in AchievementTracker({"bogus": "x"}).unlocked
    assert Statistics({"bogus": 5, "items_bought": -3})["items_bought"] == 0


def test_runner_counts_solved_stages():
    io = ScriptedIO(autopilot=True)
    ctx = MissionContext(UI(io, Theme(color=False, unicode=False), animations=False), GameRNG(2), CFG,
                         grace_ticks=200, max_ticks=500)
    run_stages(ctx, [{"type": "cipher", "params": {"kind": "binary"}},
                     {"type": "cipher", "params": {"kind": "hex"}},
                     {"type": "firewall", "params": {}}])
    assert ctx.solved == {"cipher": 2, "firewall": 1}
