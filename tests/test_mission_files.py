"""TOML mission files: loading, validation, the check command and the game wiring."""
import tomllib
from pathlib import Path

import pytest

from cyberheist import main
from cyberheist.core.game import Game
from cyberheist.interface.ui import ScriptedIO
from cyberheist.missions import loader

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "examples" / "example-mission.toml"


def example_data():
    return tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))


def write(d: Path, name: str, data: dict | str) -> Path:
    """Write a mission file from a dict (via the example's text with edits) or raw text."""
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_text(data if isinstance(data, str) else dumps(data), encoding="utf-8")
    return path


def dumps(data: dict) -> str:
    """Tiny TOML writer, enough for mission files (tomllib has no writer)."""
    def val(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, list):
            return "[" + ", ".join(val(x) for x in v) + "]"
        if isinstance(v, dict):
            return "{ " + ", ".join(f"{k} = {val(x)}" for k, x in v.items()) + " }"
        raise TypeError(v)
    lines = [f"{k} = {val(v)}" for k, v in data.items() if k not in ("stages", "optional")]
    for table in ("stages", "optional"):
        for item in data.get(table, []):
            lines += ["", f"[[{table}]]"] + [f"{k} = {val(v)}" for k, v in item.items()]
    return "\n".join(lines) + "\n"


def test_example_file_loads_and_round_trips_through_the_writer(tmp_path):
    m = loader.load_file(EXAMPLE)
    assert m.mid == 1 and [s["type"] for s in m.stages] == ["shell", "firewall", "escape"]
    assert m.stages[1]["params"] == {"pool": 6, "length": 4} and m.optional[0]["id"] == "quick"
    again = loader.load_file(write(tmp_path, "01.toml", example_data()))
    assert again == m


@pytest.mark.parametrize("edit, expected", [
    (lambda d: d.pop("title"), "missing title"),
    (lambda d: d.update(max_ticks="lots"), "max_ticks must be int"),
    (lambda d: d.update(reward_xp=True), "reward_xp must be int"),
    (lambda d: d.update(colour="red"), "unknown key 'colour'"),
    (lambda d: d.update(par_ticks=100, grace_ticks=50), "par_ticks <= grace_ticks <= max_ticks"),
    (lambda d: d.update(stages=[]), "at least one"),
    (lambda d: d.update(primary=[]), "primary must be a non-empty list"),
    (lambda d: d["stages"].append({"type": "laser"}), "type 'laser' is not one of"),
    (lambda d: d["stages"].append({"type": "cipher"}), "params.kind is required"),
    (lambda d: d["stages"].append({"type": "cipher", "params": {"kind": "rot13"}}), "kind 'rot13'"),
    (lambda d: d["stages"][1]["params"].update(pool=99), "pool = 99 is outside 4-8"),
    (lambda d: d["stages"][1]["params"].update(speed=2), "unknown param 'speed'"),
    (lambda d: d["stages"][1]["params"].update(length=6, pool=5), "length is longer than pool"),
    (lambda d: d["stages"].append({"type": "network", "params": {"target": "MOON"}}), "target must be"),
    (lambda d: d["optional"].append(dict(d["optional"][0])), "duplicate id 'quick'"),
    (lambda d: d["optional"][0].update(kind="vibes"), "kind must be one of"),
    (lambda d: d["optional"][0].pop("value"), "needs a number value"),
])
def test_validator_names_each_problem(edit, expected):
    data = example_data()
    edit(data)
    problems = loader.validate(data)
    assert any(expected in p for p in problems), problems
    with pytest.raises(loader.MissionFileError):
        loader.parse_mission(data, "x.toml")


def test_every_documented_stage_param_is_accepted():
    data = example_data()
    data["stages"] = [
        {"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8, "repeats": True, "margin": 1}},
        {"type": "cipher", "params": {"kind": "vigenere", "attempts": 3, "tough": True}},
        {"type": "password", "params": {"words": 8, "digits": 2, "symbols": 4, "range": 5, "attempts": 6,
                                        "hide_words": True, "sum_clue": True, "margin": 2}},
        {"type": "network", "params": {"target": "BACKUP", "hidden": 2, "locks": 1, "tough": True,
                                       "patrol": 0.5}},
        {"type": "escape", "params": {"rounds": 4, "slack": 4, "tough": True}},
    ]
    data["optional"].append({"id": "seen", "text": "Find a hidden node", "kind": "hidden_node",
                             "xp": 50, "credits": 50})
    assert loader.validate(data) == []


def test_load_dirs_skips_bad_files_and_reports_them(tmp_path):
    good = example_data()
    write(tmp_path / "a", "01-good.toml", good)
    write(tmp_path / "a", "02-broken.toml", "title = [unclosed")
    write(tmp_path / "a", "03-invalid.toml", {**good, "id": 3, "max_ticks": -1})
    write(tmp_path / "b", "01-clash.toml", good)
    res = loader.load_dirs(tmp_path / "a", tmp_path / "b", tmp_path / "missing")
    assert [m.mid for m in res.missions] == [1] and res.files == 4
    text = "\n".join(res.problems)
    assert "02-broken.toml: not valid TOML" in text
    assert "03-invalid.toml" in text and "01-clash.toml: id 1 is already used by 01-good.toml" in text


def test_load_dirs_warns_about_gaps_in_ids(tmp_path):
    write(tmp_path, "01.toml", example_data())
    write(tmp_path, "03.toml", {**example_data(), "id": 3})
    res = loader.load_dirs(tmp_path)
    assert [m.mid for m in res.missions] == [1, 3]
    assert any("without gaps" in p for p in res.problems)


def test_file_with_byte_order_mark_loads(tmp_path):
    path = tmp_path / "01.toml"
    path.write_text("﻿" + EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert loader.load_file(path).title == "Practice Run"


def test_playtest_flags_a_mission_with_no_time_to_finish(tmp_path):
    ok = loader.load_file(EXAMPLE)
    assert loader.playtest(ok, range(2), ("easy",)) == {"easy": (2, 2)}
    tight = loader.parse_mission({**example_data(), "par_ticks": 1, "grace_ticks": 1, "max_ticks": 3})
    assert loader.playtest(tight, range(2), ("easy",)) == {"easy": (0, 2)}
    write(tmp_path, "01.toml", {**example_data(), "par_ticks": 1, "grace_ticks": 1, "max_ticks": 3})
    lines, all_ok = loader.check_report([tmp_path], seeds=1)
    assert not all_ok and "TOO HARD" in "\n".join(lines)


def test_check_missions_command_exit_codes(tmp_path, capsys):
    good = tmp_path / "good"
    write(good, "01.toml", example_data())
    assert main.main(["--check-missions", str(good)]) == 0
    assert "All missions look good." in capsys.readouterr().out
    bad = tmp_path / "bad"
    write(bad, "01.toml", {**example_data(), "tier": 5})
    assert main.main(["--check-missions", str(bad)]) == 1
    assert "PROBLEM  01.toml: tier must be str" in capsys.readouterr().out
    assert main.main(["--check-missions", str(tmp_path / "empty")]) == 0
    assert "No mission files found" in capsys.readouterr().out


def test_game_plays_a_mission_loaded_from_a_file(tmp_path, monkeypatch):
    missions_dir = tmp_path / "missions"
    write(missions_dir, "01.toml", example_data())
    write(missions_dir, "02.toml", "nonsense = ")
    monkeypatch.setattr(loader, "BUNDLED_DIR", missions_dir)
    monkeypatch.setattr(loader, "USER_DIR", tmp_path / "none")
    io = ScriptedIO(["Neo_01", "3", "1", "y", "8"], autopilot=True)
    g = Game(io, tmp_path / "save.db", seed=3)
    assert [m.title for m in g.missions] == ["Practice Run"] and len(g.mission_problems) == 1
    g.run()
    text = io.text()
    assert "1 problem(s) in mission files" in text and "PRACTICE RUN" in text.upper()
    assert g.progress[1]["clears"] == 1
