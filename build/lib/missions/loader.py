"""Load campaign missions from TOML files and check them before they reach the game.

One mission per ``.toml`` file. The game reads the bundled ``missions/campaign/`` folder
and then ``~/.cyberheist/missions/``. See docs/mission-format.md for the format.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from challenges import encryption, network
from missions.mission_runner import STAGES, Mission

BUNDLED_DIR = Path(__file__).resolve().parent / "campaign"
USER_DIR = Path.home() / ".cyberheist" / "missions"

REQUIRED: dict[str, type | tuple[type, ...]] = {
    "id": int, "title": str, "tier": str, "intro": str, "briefing": str, "primary": list,
    "par_ticks": int, "grace_ticks": int, "max_ticks": int, "reward_xp": int,
    "reward_credits": int, "completion": str, "stages": list,
}
OPTIONAL: dict[str, type | tuple[type, ...]] = {"optional": list, "failure": list, "events": bool}

# Allowed params per stage type: name -> (type, min, max). None means no bound.
INT, BOOL = int, bool
PARAMS: dict[str, dict[str, tuple[Any, ...]]] = {
    "shell": {},
    "firewall": {"pool": (INT, 4, 8), "length": (INT, 3, 6), "attempts": (INT, 1, 20),
                 "repeats": (BOOL,), "margin": (INT, 0, 10)},
    "cipher": {"kind": (str,), "attempts": (INT, 1, 10), "tough": (BOOL,)},
    "password": {"words": (INT, 4, 20), "digits": (INT, 1, 4), "symbols": (INT, 2, 8),
                 "range": (INT, 2, 10), "attempts": (INT, 1, 20), "hide_words": (BOOL,),
                 "sum_clue": (BOOL,), "margin": (INT, 0, 10)},
    "network": {"target": (str,), "hidden": (INT, 0, len(network.HIDDEN)),
                "locks": (INT, 0, 2), "tough": (BOOL,)},
    "escape": {"rounds": (INT, 1, 8), "slack": (INT, 0, 20), "tough": (BOOL,)},
}
COMMON_PARAMS = {"patrol": ((int, float), 0, 5)}
OPTIONAL_KINDS = ("max_ticks", "max_detection", "hidden_node", "no_wrong")
TARGETS = ("DATABASE", "BACKUP")


class MissionFileError(ValueError):
    """A mission file that can't be used. ``problems`` lists every issue found."""

    def __init__(self, source: str, problems: list[str]):
        super().__init__(f"{source}: " + "; ".join(problems))
        self.source, self.problems = source, problems


@dataclass
class LoadResult:
    """Missions that loaded, plus the problems that kept others out."""

    missions: list[Mission] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    files: int = 0


def _type_name(t: type | tuple[type, ...]) -> str:
    return " or ".join(x.__name__ for x in t) if isinstance(t, tuple) else t.__name__


def _is(value: Any, t: type | tuple[type, ...]) -> bool:
    """isinstance, except a bool never counts as an int (TOML keeps them apart)."""
    if isinstance(value, bool) and t is not bool and not (isinstance(t, tuple) and bool in t):
        return False
    return isinstance(value, t)


def _check_stage(n: int, stage: Any) -> list[str]:
    where = f"stage {n}"
    if not isinstance(stage, dict):
        return [f"{where}: must be a table"]
    kind = stage.get("type")
    if kind not in STAGES:
        return [f"{where}: type {kind!r} is not one of {', '.join(STAGES)}"]
    out = []
    for key in stage:
        if key not in ("type", "label", "params"):
            out.append(f"{where}: unknown key {key!r}")
    if "label" in stage and not isinstance(stage["label"], str):
        out.append(f"{where}: label must be text")
    params = stage.get("params", {})
    if not isinstance(params, dict):
        return out + [f"{where}: params must be a table"]
    allowed = {**PARAMS[kind], **COMMON_PARAMS}
    for key, value in params.items():
        spec = allowed.get(key)
        if spec is None:
            out.append(f"{where} ({kind}): unknown param {key!r}; allowed: {', '.join(allowed)}")
            continue
        if not _is(value, spec[0]):
            out.append(f"{where} ({kind}): {key} must be {_type_name(spec[0])}")
        elif len(spec) == 3 and not spec[1] <= value <= spec[2]:
            out.append(f"{where} ({kind}): {key} = {value} is outside {spec[1]}-{spec[2]}")
    if kind == "cipher":
        if "kind" not in params:
            out.append(f"{where} (cipher): params.kind is required ({', '.join(encryption.KINDS)})")
        elif params["kind"] not in encryption.KINDS:
            out.append(f"{where} (cipher): kind {params['kind']!r} is not one of {', '.join(encryption.KINDS)}")
    if kind == "network" and params.get("target", "DATABASE") not in TARGETS:
        out.append(f"{where} (network): target must be one of {', '.join(TARGETS)}")
    if kind == "firewall" and params.get("length", 4) > params.get("pool", 6) and not params.get("repeats"):
        out.append(f"{where} (firewall): length is longer than pool; set repeats = true or shorten it")
    return out


def _check_optional(n: int, opt: Any, seen: set[str]) -> list[str]:
    where = f"optional {n}"
    if not isinstance(opt, dict):
        return [f"{where}: must be a table"]
    out = []
    for key, t in (("id", str), ("text", str), ("kind", str), ("xp", int), ("credits", int)):
        if key not in opt:
            out.append(f"{where}: missing {key}")
        elif not _is(opt[key], t):
            out.append(f"{where}: {key} must be {_type_name(t)}")
    if opt.get("kind") not in OPTIONAL_KINDS:
        out.append(f"{where}: kind must be one of {', '.join(OPTIONAL_KINDS)}")
    elif opt["kind"] != "hidden_node" and not _is(opt.get("value"), (int, float)):
        out.append(f"{where}: {opt['kind']} needs a number value")
    if isinstance(opt.get("id"), str):
        if opt["id"] in seen:
            out.append(f"{where}: duplicate id {opt['id']!r}")
        seen.add(opt["id"])
    return out


def validate(data: dict[str, Any]) -> list[str]:
    """Every problem with one mission's data. An empty list means it's usable."""
    out = []
    for key, t in REQUIRED.items():
        if key not in data:
            out.append(f"missing {key}")
        elif not _is(data[key], t):
            out.append(f"{key} must be {_type_name(t)}")
    for key, t in OPTIONAL.items():
        if key in data and not _is(data[key], t):
            out.append(f"{key} must be {_type_name(t)}")
    for key in data:
        if key not in REQUIRED and key not in OPTIONAL:
            out.append(f"unknown key {key!r}")
    if out:
        return out
    if data["id"] < 1:
        out.append("id must be 1 or more")
    for key in ("par_ticks", "grace_ticks", "max_ticks", "reward_xp", "reward_credits"):
        if data[key] < 0:
            out.append(f"{key} can't be negative")
    if not data["par_ticks"] <= data["grace_ticks"] <= data["max_ticks"]:
        out.append("ticks must satisfy par_ticks <= grace_ticks <= max_ticks")
    if not data["primary"] or not all(isinstance(p, str) for p in data["primary"]):
        out.append("primary must be a non-empty list of text")
    if not all(isinstance(p, str) for p in data.get("failure", [])):
        out.append("failure must be a list of text")
    if not data["stages"]:
        out.append("stages must have at least one [[stages]] entry")
    for n, stage in enumerate(data["stages"], 1):
        out += _check_stage(n, stage)
    seen: set[str] = set()
    for n, opt in enumerate(data.get("optional", []), 1):
        out += _check_optional(n, opt, seen)
    return out


def parse_mission(data: dict[str, Any], source: str = "<data>") -> Mission:
    """Turn checked TOML data into a Mission. Raises MissionFileError."""
    problems = validate(data)
    if problems:
        raise MissionFileError(source, problems)
    extra = {k: data[k] for k in ("failure", "events") if k in data}
    return Mission(
        mid=data["id"], title=data["title"], tier=data["tier"], intro=data["intro"],
        briefing=data["briefing"], primary=list(data["primary"]),
        optional=[dict(o) for o in data.get("optional", [])],
        stages=[{"type": s["type"], **({"label": s["label"]} if "label" in s else {}),
                 "params": dict(s.get("params", {}))} for s in data["stages"]],
        par_ticks=data["par_ticks"], grace_ticks=data["grace_ticks"], max_ticks=data["max_ticks"],
        reward_xp=data["reward_xp"], reward_credits=data["reward_credits"],
        completion=data["completion"], **extra)


def load_file(path: Path) -> Mission:
    """Read and check one mission file. Raises MissionFileError."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise MissionFileError(path.name, [f"can't read file ({exc})"]) from exc
    except tomllib.TOMLDecodeError as exc:
        raise MissionFileError(path.name, [f"not valid TOML ({exc})"]) from exc
    return parse_mission(data, path.name)


def load_dirs(*dirs: Path) -> LoadResult:
    """Load every ``*.toml`` in the folders, in order. Later folders can't reuse an id.

    Bad files are reported and skipped rather than stopping the game.
    """
    result, owner = LoadResult(), {}
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.toml")):
            result.files += 1
            try:
                m = load_file(path)
            except MissionFileError as exc:
                result.problems += [f"{exc.source}: {p}" for p in exc.problems]
                continue
            if m.mid in owner:
                result.problems.append(f"{path.name}: id {m.mid} is already used by {owner[m.mid]}")
                continue
            owner[m.mid] = path.name
            result.missions.append(m)
    result.missions.sort(key=lambda m: m.mid)
    ids = [m.mid for m in result.missions]
    if ids and ids != list(range(1, len(ids) + 1)):
        result.problems.append(f"mission ids should run 1, 2, 3... without gaps; found {ids}")
    return result


def playtest(mission: Mission, seeds: range = range(5),
             difficulties: tuple[str, ...] = ("easy", "normal", "hard")) -> dict[str, tuple[int, int]]:
    """Play the mission with the logic-perfect autopilot. Returns {difficulty: (wins, runs)}.

    A mission the autopilot can't clear on Easy is almost certainly broken: the tick
    budget is too small or the locks are too tight for the stages.
    """
    from core.rng import GameRNG
    from core.state import load_config
    from interface.theme import Theme
    from interface.ui import UI, ScriptedIO
    from missions.mission_runner import run_mission
    cfg, out = load_config(), {}
    for diff in difficulties:
        wins = 0
        for seed in seeds:
            ui = UI(ScriptedIO(autopilot=True), Theme(color=False), animations=False)
            wins += run_mission(ui, GameRNG(seed * 7919 + mission.mid), cfg, mission, diff).success
        out[diff] = (wins, len(seeds))
    return out


def check_report(dirs: list[Path], seeds: int = 5) -> tuple[list[str], bool]:
    """Text report for ``cyberheist --check-missions``. Returns (lines, all_ok)."""
    res = load_dirs(*dirs)
    lines = [f"Checked {res.files} mission file(s) in: " + ", ".join(str(d) for d in dirs)]
    ok = not res.problems
    for p in res.problems:
        lines.append(f"  PROBLEM  {p}")
    for m in res.missions:
        results = playtest(m, range(seeds))
        cells = "  ".join(f"{d} {w}/{n}" for d, (w, n) in results.items())
        verdict = "ok"
        if results.get("easy", (1, 1))[0] < results.get("easy", (1, 1))[1]:
            verdict, ok = "TOO HARD", False
        lines.append(f"  {m.mid:02d} {m.title[:30]:<30} {len(m.stages)} stage(s)  autopilot: {cells}  {verdict}")
    if res.files == 0:
        lines.append("  No mission files found. See docs/mission-format.md to write one.")
    lines.append("All missions look good." if ok and res.missions else
                 "Fix the problems above." if not ok else "")
    return [line for line in lines if line], ok
