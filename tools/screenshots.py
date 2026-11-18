"""Generate the README screenshots: runs real game scenes and renders the coloured output to SVG.

Usage: python tools/screenshots.py   (writes docs/screenshots/*.svg)
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from challenges import encryption, firewall  # noqa: E402
from core.game import MAIN_OPTIONS  # noqa: E402
from core.player import Player  # noqa: E402
from core.progression import RewardBreakdown  # noqa: E402
from core.rng import GameRNG  # noqa: E402
from core.state import load_config  # noqa: E402
from interface import animations, screens  # noqa: E402
from interface.menus import Menu  # noqa: E402
from interface.theme import Theme  # noqa: E402
from interface.ui import UI  # noqa: E402
from missions.mission_runner import Mission, MissionContext, MissionResult, run_stages  # noqa: E402
from systems.achievements import ACHIEVEMENTS, notify  # noqa: E402
from systems.black_market import BlackMarket  # noqa: E402
from systems.inventory import Inventory  # noqa: E402
from systems.statistics import Statistics  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
CFG = load_config()
ANSI = re.compile(r"\033\[([0-9;]*)m")
COLORS = {"32": "#2ea043", "33": "#d29922", "36": "#39c5cf", "90": "#6e7681", "91": "#ff6b6b",
          "92": "#3fff8b", "93": "#ffd866", "95": "#ff79c6", "96": "#5ce1e6", "97": "#f0f6fc"}
DEFAULT = "#c9d1d9"
TYPED = "#f0f6fc"


class CaptureIO:
    """Records raw output (ANSI kept). Inputs come from a script, then from the autopilot."""

    autopilot = True

    def __init__(self, inputs: list[str] | None = None) -> None:
        self.queue = list(inputs or [])
        self.buf = ""

    def write(self, text: str = "", end: str = "\n") -> None:
        self.buf += text + end

    def read(self, prompt: str, auto: Callable[[], str] | None = None) -> str:
        answer = self.queue.pop(0) if self.queue else (auto() if auto else "")
        self.buf += prompt + f"\033[97m{answer}\033[0m\n"
        return answer

    def sleep(self, seconds: float) -> None:
        pass

    def bell(self) -> None:
        pass

    def clear(self) -> None:
        self.buf += "\033[90m   ... screen cleared ...\033[0m\n"

    def lines(self) -> list[str]:
        return self.buf.rstrip("\n").split("\n")


def make_ui(io: CaptureIO, animations_on: bool = False) -> UI:
    return UI(io, Theme("green", color=True, unicode=True), typewriter=False, animations=animations_on)


def to_svg(lines: list[str], title: str, cols: int = 80) -> str:
    """Render ANSI-coloured lines as a terminal-window SVG."""
    cw, lh, pad, top = 8.4, 18.0, 18.0, 40.0
    width = cols * cw + pad * 2
    height = top + len(lines) * lh + pad
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}">',
           f'<rect width="100%" height="100%" rx="10" fill="#0b0f14"/>',
           f'<rect width="100%" height="30" rx="10" fill="#161b22"/>',
           f'<rect y="20" width="100%" height="10" fill="#161b22"/>',
           '<circle cx="18" cy="15" r="6" fill="#ff5f56"/><circle cx="38" cy="15" r="6" fill="#ffbd2e"/>'
           '<circle cx="58" cy="15" r="6" fill="#27c93f"/>',
           f'<text x="{width / 2:.0f}" y="19" fill="#8b949e" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
           f'font-size="12" text-anchor="middle">{escape(title)}</text>',
           '<g font-family="Cascadia Mono, Consolas, DejaVu Sans Mono, Menlo, monospace" font-size="14" '
           'xml:space="preserve">']
    for row, line in enumerate(lines):
        y = top + (row + 0.8) * lh
        col, color, bold = 0, DEFAULT, False
        parts = ANSI.split(line)
        spans = []
        for i, chunk in enumerate(parts):
            if i % 2 == 1:
                for code in (chunk or "0").split(";"):
                    if code == "0":
                        color, bold = DEFAULT, False
                    elif code == "1":
                        bold = True
                    elif code in COLORS:
                        color = COLORS[code]
                continue
            if not chunk:
                continue
            weight = ' font-weight="bold"' if bold else ""
            # Non-breaking spaces: SVG collapses ordinary runs of spaces, which breaks alignment.
            text = escape(chunk).replace(" ", " ")
            # Pin each run to an exact cell width so box-drawing glyphs line up whatever the font.
            spans.append(f'<tspan x="{pad + col * cw:.1f}" textLength="{len(chunk) * cw:.1f}" '
                         f'lengthAdjust="spacingAndGlyphs" fill="{color}"{weight}>{text}</tspan>')
            col += len(chunk)
        if spans:
            out.append(f'<text y="{y:.1f}">{"".join(spans)}</text>')
    out.append("</g></svg>")
    return "\n".join(out)


# -- scenes -------------------------------------------------------------------------
def scene_boot() -> CaptureIO:
    io = CaptureIO()
    ui = make_ui(io, animations_on=True)
    animations.boot_sequence(ui, 3.0)
    screens.logo(ui)
    return io


def scene_menu() -> CaptureIO:
    io = CaptureIO(["05"])
    ui = make_ui(io)
    screens.logo(ui)
    ui.ok("Welcome back, Neo_01.")
    m = Menu("MAIN MENU", MAIN_OPTIONS, allow_back=False)
    m.choose(ui)
    return io


def stage(stages: list[dict], inputs: list[str] | None = None, seed: int = 11, **kw) -> CaptureIO:
    io = CaptureIO(inputs)
    ctx = MissionContext(make_ui(io), GameRNG(seed), CFG, grace_ticks=60, max_ticks=200, **kw)
    run_stages(ctx, stages)
    return io


def scene_firewall() -> CaptureIO:
    return stage([{"type": "firewall", "label": "Gate firewall", "params": {"pool": 7, "length": 4}}], seed=21)


def scene_cipher() -> CaptureIO:
    seed = 5
    p = encryption.generate(GameRNG(seed).fork("cipher-vigenere"), "vigenere", 3, tough=True)
    key = encryption.key_from_crib(p.ciphertext, p.crib, p.key_len)
    return stage([{"type": "cipher", "label": "Intercepted transmission", "params": {"kind": "vigenere"}}],
                 ["hint", f"apply {key}"], seed=seed)


def scene_network() -> CaptureIO:
    return stage([{"type": "network", "label": "Silent mapping", "params": {"hidden": 1}}],
                 ["scan"] * 5 + ["map", "routes", "route 1"], seed=3)


def scene_password() -> CaptureIO:
    return stage([{"type": "password", "label": "Admin passphrase", "params": {}}], seed=8)


def scene_escape() -> CaptureIO:
    return stage([{"type": "escape", "label": "Exfiltration", "params": {"rounds": 4}}], seed=9)


def scene_market() -> CaptureIO:
    io = CaptureIO()
    ui = make_ui(io)
    inv = Inventory(CFG["items"], 2)
    for iid in ("ghost_proxy", "cipher_toolkit", "quantum_decoder"):
        inv.add(iid)
    inv.equip("ghost_proxy")
    market = BlackMarket(CFG["items"])
    ui.box("BLACK MARKET", ["Credits: 4,250", "Commands: buy N, equip N, unequip N, b. Max 2 passives equipped."])
    ui.table(["#", "ITEM", "PRICE", "KIND", "USES", "OWNED"], [r[:6] for r in market.listing(inv)])
    io.read(ui.paint("market> "), lambda: "buy 3")
    ui.ok("Bought Neural Accelerator for 2,500 cr.")
    return io


def scene_profile() -> CaptureIO:
    io = CaptureIO()
    ui = make_ui(io)
    p = Player(alias="Neo_01", xp=3150, credits=4250, reputation=64, missions_completed=5, successes=7,
               failures=2, play_ticks=412, play_seconds=3720, last_seed=1840027761)
    p.refresh_level(CFG["progression"]["xp_thresholds"])
    inv = Inventory(CFG["items"], 2)
    inv.add("ghost_proxy")
    inv.equip("ghost_proxy")
    stats = Statistics()
    for mid, ok, t, peak in [(1, True, 5, 0), (2, True, 14, 24), (3, False, 31, 100), (3, True, 11, 9),
                             (4, True, 26, 38), (5, True, 33, 52), (6, False, 40, 100), (6, True, 37, 61)]:
        solved = {"cipher": 2, "firewall": 1, "password": 1, "network": 1, "escape": 1} if ok else {"cipher": 1}
        stats.record_mission(mid, ok, t, 20, peak, 2, solved, 1, 900 if ok else 0)
    stats.bump("items_bought", 9)
    screens.profile(ui, p, CFG, inv)
    screens.statistics(ui, stats)
    return io


def scene_complete() -> CaptureIO:
    io = CaptureIO()
    ui = make_ui(io)
    m = Mission(2, "Training Run", "Beginner", "", "", [], [], [], par_ticks=16, grace_ticks=40, max_ticks=90,
                reward_xp=250, reward_credits=800, completion="Gate open. The client noticed.")
    r = MissionResult(True, "", 12, 0, 0, ["clean"], {"firewall": 1}, [], 250)
    rw = RewardBreakdown()
    rw.add("Primary objectives", 250, 800)
    rw.add("Optional: Keep detection under 40%", 75, 200)
    rw.add("GHOST MODE (zero detection)", 150, 500)
    rw.add("SPEED DEMON (beat par)", 100, 300)
    rw.add("Recovered backups / bonus files", 0, 250)
    screens.completion(ui, m, r, rw)
    notify(ui, [ACHIEVEMENTS[1]])
    ui.ok("RANK UP: 3 Ghost Operator")
    return io


def scene_daily() -> CaptureIO:
    import datetime as dt
    from interface.ui import ScriptedIO
    from missions.mission_runner import run_mission
    from systems.daily import build_daily, daily_seed, run_seed, score_run
    day = dt.date(2026, 11, 18)
    m = build_daily(day)
    quiet = UI(ScriptedIO(autopilot=True), Theme(color=False), animations=False)
    r = run_mission(quiet, GameRNG(run_seed(day)), CFG, m, "normal")
    breakdown = score_run(r, m.par_ticks)
    io = CaptureIO()
    ui = make_ui(io)
    rows = [{"seed": daily_seed(day), "best": breakdown.total, "ticks": r.ticks, "peak": r.peak, "plays": 2},
            {"seed": 20261117, "best": 712, "ticks": 64, "peak": 31, "plays": 1},
            {"seed": 20261116, "best": 488, "ticks": 81, "peak": 52, "plays": 3}]
    screens.daily_score(ui, breakdown, breakdown.total, True)
    screens.daily_board(ui, rows, daily_seed(day), "normal")
    return io


def scene_debrief() -> list[str]:
    """A firewall stage with a careless repeat probe, its debrief, and the run summary."""
    from missions.mission_runner import Mission, run_mission
    seed = 11
    p = firewall.generate(GameRNG(seed).fork("firewall"), 6, 4, 8, margin=3)
    miss = next(c for c in firewall.candidates(6, 4, False) if firewall.score(c, p.secret) == (1, 1))
    probe = " ".join(str(i + 1) for i in miss)
    m = Mission(mid=4, title="Debrief", tier="Demo", intro="", briefing="", primary=["x"], optional=[],
                stages=[{"type": "firewall", "label": "Gate firewall", "params": {"margin": 3}},
                        {"type": "escape", "label": "Exfiltration", "params": {"rounds": 3}}],
                par_ticks=30, grace_ticks=60, max_ticks=200, reward_xp=0, reward_credits=0,
                completion="", events=False)
    io = CaptureIO([probe, probe])
    run_mission(make_ui(io), GameRNG(seed), CFG, m, "normal")
    lines = io.lines()
    first = next(i for i, line in enumerate(lines) if "DEBRIEF" in line)
    second = next(i for i, line in enumerate(lines) if "DEBRIEF: STAGE 2" in line)
    return lines[first - 6:first + 8] + lines[second:]


SCENES = {
    "01-boot": ("Boot sequence", scene_boot, None),
    "02-main-menu": ("Main menu", scene_menu, None),
    "03-firewall": ("Firewall puzzle", scene_firewall, 40),
    "04-cipher-lab": ("Cipher lab", scene_cipher, None),
    "05-network-map": ("Network mapping", scene_network, None),
    "06-password": ("Password recovery", scene_password, 36),
    "07-escape": ("Escape sequence", scene_escape, None),
    "08-black-market": ("Black market", scene_market, None),
    "09-profile": ("Hacker profile and statistics", scene_profile, None),
    "10-mission-complete": ("Mission complete", scene_complete, None),
    "11-daily-challenge": ("Daily challenge score", scene_daily, None),
    "12-debrief": ("Run debrief", scene_debrief, None),
}


def main() -> None:
    """Render every scene to docs/screenshots."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (title, fn, limit) in SCENES.items():
        got = fn()
        lines = got if isinstance(got, list) else got.lines()
        if limit:
            lines = lines[:limit]
        (OUT / f"{name}.svg").write_text(to_svg(lines, f"cyberheist — {title}"), encoding="utf-8")
        print(f"{name}.svg  {len(lines)} lines")


if __name__ == "__main__":
    main()
