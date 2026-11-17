"""Theme fallback, NO_COLOR, animation timing, menus and 80-column layout."""
from core.player import Player
from core.state import Settings, load_config
from interface import animations, screens
from interface.menus import Menu
from interface.theme import Theme
from interface.ui import UI, ScriptedIO, visible_len
from systems.inventory import Inventory
from systems.statistics import Statistics

CFG = load_config()


class TimedIO(ScriptedIO):
    """Adds up requested sleep time instead of sleeping."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.slept = 0.0

    def sleep(self, seconds):
        self.slept += seconds


def test_ascii_fallback_when_encoding_cannot_print_box_chars():
    class Ascii:
        encoding = "ascii"
    from interface.theme import supports_unicode
    assert not supports_unicode(Ascii())
    io = ScriptedIO()
    UI(io, Theme(unicode=False, color=False)).box("T", ["x"])
    assert io.output[0].startswith("+=") and all(ord(c) < 128 for c in io.text())


def test_no_color_env_disables_ansi(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert Theme().paint("hi", "danger") == "hi"
    monkeypatch.delenv("NO_COLOR")
    assert Theme(color=True).paint("hi", "danger") != "hi"


def test_boot_is_skipped_when_animations_off_and_under_4s_when_on():
    off = TimedIO()
    animations.boot_sequence(UI(off, Theme(color=False), animations=False), 3.0)
    assert off.output == [] and off.slept == 0
    on = TimedIO()
    animations.boot_sequence(UI(on, Theme(color=False), animations=True), CFG["ui"]["boot_seconds"])
    assert 0 < on.slept < 4.0


def test_menu_accepts_numbers_labels_back_and_help():
    m = Menu("T", [("a", "ALPHA"), ("b2", "BETA")])
    assert m.resolve("1") == "a" and m.resolve("02") == "b2" and m.resolve("beta") == "b2"
    assert m.resolve("3") is None and m.resolve("zzz") is None
    io = ScriptedIO(["?", "9", "b"])
    assert m.choose(UI(io, Theme(color=False))) is None
    assert "Pick 1-2" in io.text()


def test_screens_fit_80_columns():
    io = ScriptedIO()
    ui = UI(io, Theme(color=False, unicode=True), animations=False)
    screens.logo(ui)
    screens.profile(ui, Player(alias="Abcdefghijklmnop", xp=12345, credits=999999), CFG,
                    Inventory(CFG["items"], 2))
    screens.statistics(ui, Statistics())
    assert max(visible_len(line) for line in io.output) <= 80


def test_mission_hud_fits_80_columns():
    from core.rng import GameRNG
    from missions.mission_runner import MissionContext
    io = ScriptedIO()
    ctx = MissionContext(UI(io, Theme(color=True, unicode=True), animations=False), GameRNG(1), CFG,
                         max_ticks=1000)
    ctx.objective = "A very long objective description that would never fit on one terminal line at all"
    ctx.ticks, ctx.meter.level = 999, 99.5
    ctx.hud()
    line = io.output[-1]
    assert visible_len(line) <= 80 and line.endswith("...") and "CRITICAL" in line


def test_settings_validation():
    s = Settings(CFG["defaults"], {"theme": "pink", "difficulty": "hard", "animation_speed": 99})
    assert s.get("theme") == "green" and s.get("difficulty") == "hard" and s.get("animation_speed") == 1.0
