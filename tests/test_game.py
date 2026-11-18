"""End-to-end game loop with a scripted input harness. Uses small test missions."""
import pytest

from core.game import Game
from database.database import SaveManager
from interface.ui import ScriptedIO
from missions.mission_runner import Mission

SHELL = {"type": "shell", "label": "Orientation"}
SHELL_INPUTS = ["scan", "connect train-01", "cat welcome.txt"]


def mission(mid, stages, **kw):
    base = dict(tier="Test", intro="Test intro.", briefing="Test briefing.", primary=["Clear it"],
                optional=[{"id": "fast", "text": "Under 50 ticks", "kind": "max_ticks", "value": 50,
                           "xp": 10, "credits": 10}],
                par_ticks=2, grace_ticks=100, max_ticks=300, reward_xp=100, reward_credits=400,
                completion="Done.", events=False)
    base.update(kw)
    return Mission(mid, f"Test Op {mid}", stages=stages, **base)


MISSIONS = [mission(1, [SHELL]), mission(2, [SHELL, SHELL]),
            mission(3, [{"type": "cipher", "params": {"kind": "hex", "attempts": 2}}])]


class InterruptIO(ScriptedIO):
    """Raises KeyboardInterrupt (like Ctrl+C) when it reaches the '^C' input."""

    def read(self, prompt, auto=None):
        if self.queue and self.queue[0] == "^C":
            self.queue.popleft()
            raise KeyboardInterrupt
        return super().read(prompt, auto)


def run(tmp_path, inputs, autopilot=False, io_cls=ScriptedIO, missions=MISSIONS, seed=7):
    io = io_cls(inputs, autopilot=autopilot)
    g = Game(io, tmp_path / "save.db", seed=seed, missions=missions)
    g.run()
    return g, io


def test_registration_validates_and_profile_survives_restart(tmp_path):
    g, io = run(tmp_path, ["ab", "bad alias!", "Neo_01", "8"])
    out = io.text()
    assert "at least 3" in out and "letters, digits" in out and "Identity Neo_01 registered" in out
    g2, io2 = run(tmp_path, ["8"])
    assert g2.player.alias == "Neo_01" and "Welcome back, Neo_01" in io2.text()


def test_corrupted_save_is_quarantined(tmp_path):
    (tmp_path / "save.db").write_bytes(b"garbage" * 500)
    g, io = run(tmp_path, ["Trinity", "8"])
    assert "Save file was damaged" in io.text() and g.player.alias == "Trinity"
    assert list(tmp_path.glob("save.corrupt-*.db"))


def test_every_main_menu_option(tmp_path):
    inputs = [
        "Neo_01",
        "02",                                   # CONTINUE: plays mission 1 (autopilot)
        "3", "9", "3", "?", "2",                # DATABASE: bad number, locked, help, then play mission 2
        "4", "buy 1", "equip 1", "unequip 1", "buy 99", "?", "sell 1", "b",  # MARKET
        "5", "x", "s", "b",                     # PROFILE + manual save
        "6",                                    # ACHIEVEMENTS
        "7", "1", "2", "7", "8", "9", "b",      # SETTINGS: difficulty, theme, adaptive, debrief, reset, back
        "1", "y", "Morpheus",                   # NEW GAME: confirm wipe, re-register, plays mission 1
        "8",                                    # EXIT
    ]
    g, io = run(tmp_path, inputs, autopilot=True)
    out = io.text()
    assert out.count("MISSION COMPLETE") == 3
    assert "No mission with that number" in out and "Locked" in out
    assert "Bought Ghost Proxy" in out and "Ghost Proxy equipped" in out and "unequipped" in out
    assert "Commands: buy N" in out and "Game saved." in out and "First Breach" in out
    assert "Setting saved." in out and "Progress saved" in out
    assert g.player.alias == "Morpheus" and g.player.missions_completed == 1
    assert g.settings.get("difficulty") == "normal"            # reset restored defaults
    assert g.progress[2]["status"] == "available" and g.progress[3]["status"] == "locked"


def test_unlock_order_and_rewards(tmp_path):
    g, _ = run(tmp_path, ["Neo_01", "2", "2", "8"], autopilot=True)
    assert [g.progress[i]["status"] for i in (1, 2, 3)] == ["completed", "completed", "available"]
    assert g.player.successes == 2 and g.player.credits > 1000 and g.player.xp > 0
    assert g.stats["missions_won"] == 2 and "first_breach" in g.tracker.unlocked


def test_failure_screen_and_counters(tmp_path):
    three = [m for m in MISSIONS if m.mid == 3]
    g, io = run(tmp_path, ["Neo_01", "2", "y", "wrong", "wrong", "", "8"], missions=three)
    assert "CONNECTION TERMINATED" in io.text()
    assert g.player.failures == 1 and g.progress[3]["status"] == "available" and g.stats["streak"] == 0


def test_pause_menu_abort_counts_as_failure(tmp_path):
    two = [mission(1, [SHELL, SHELL])]
    g, io = run(tmp_path, ["Neo_01", "2", "y", *SHELL_INPUTS, "p", "2", "", "8"], missions=two)
    assert "aborted by operator" in io.text() and g.player.failures == 1


def test_ctrl_c_saves_and_checkpoint_resumes(tmp_path):
    two = [mission(1, [SHELL, SHELL])]
    g, io = run(tmp_path, ["Neo_01", "4", "buy 2", "b", "2", "y", *SHELL_INPUTS, "^C"],
                io_cls=InterruptIO, missions=two)
    assert "Saving progress" in io.text()
    sm = SaveManager(tmp_path / "save.db")
    sm.open()
    assert sm.load_inventory()["cipher_toolkit"]["uses"] == 5
    assert sm.load_missions()[1]["checkpoint"]["stage"] == 1
    sm.close()
    g2, io2 = run(tmp_path, ["2", "y", "y", *SHELL_INPUTS, "", "8"], missions=two)
    out = io2.text()
    assert "Resume Test Op 1 from stage 2" in out and "STAGE 1/2" not in out and "MISSION COMPLETE" in out
    assert g2.progress[1]["checkpoint"] is None


def test_end_of_input_saves_and_quits_without_inventing_an_alias(tmp_path, monkeypatch):
    from interface import ui as ui_mod
    feed = iter(["﻿Neo_01"])

    def fake_input(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None
    monkeypatch.setattr("builtins.input", fake_input)
    g = Game(ui_mod.ConsoleIO(), tmp_path / "save.db", seed=1, missions=MISSIONS)
    g.run()
    sm = SaveManager(tmp_path / "save.db")
    sm.open()
    assert sm.load_profile().alias == "Neo_01"
    sm.close()


def test_error_boundary_keeps_game_running(tmp_path, monkeypatch):
    def boom(self):
        raise ValueError("synthetic failure")
    monkeypatch.setattr(Game, "achievements", boom)
    g, io = run(tmp_path, ["Neo_01", "6", "8"])
    assert "Something glitched: ValueError: synthetic failure" in io.text() and "seed 7" in io.text()


def test_missing_campaign_is_reported(tmp_path):
    g, io = run(tmp_path, ["Neo_01", "2", "3", "b", "8"], missions=[])
    assert io.text().count("No missions are installed") == 2


def test_new_game_can_be_cancelled(tmp_path):
    g, io = run(tmp_path, ["Neo_01", "2", "1", "n", "8"], autopilot=True)
    assert "Kept your current profile" in io.text() and g.player.alias == "Neo_01"


def test_debrief_setting_shows_and_hides_the_stage_report(tmp_path):
    two = [mission(1, [SHELL, SHELL])]
    g, io = run(tmp_path / "on", ["Neo_01", "2", "y", "8"], autopilot=True, missions=two)
    assert g.settings.get("debrief") is True
    assert io.text().count("DEBRIEF: STAGE") == 2 and "RUN SUMMARY" in io.text()
    g, io = run(tmp_path / "off", ["Neo_01", "7", "8", "b", "2", "y", "8"], autopilot=True, missions=two)
    assert g.settings.get("debrief") is False
    assert "DEBRIEF" not in io.text() and g.progress[1]["clears"] == 1
