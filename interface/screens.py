"""Full screens: logo, briefing, profile, statistics, achievements, map, results."""
from __future__ import annotations

from typing import Any

from interface.ui import UI, wrap

LOGO = [
    r"  ______   ______  _____ ____  _   _ _____ ___ ____ _____ ",
    r" / ___\ \ / / __ )| ____|  _ \| | | | ____|_ _/ ___|_   _|",
    r"| |    \ V /|  _ \|  _| | |_) | |_| |  _|  | |\___ \ | |  ",
    r"| |___  | | | |_) | |___|  _ <|  _  | |___ | | ___) || |  ",
    r" \____| |_| |____/|_____|_| \_\_| |_|_____|___|____/ |_|  ",
]
SUBTITLE = "THE TERMINAL BREAK-IN"
TAGLINE = "THINK LIKE A HACKER. MOVE LIKE A GHOST. LEAVE NO TRACE."


def logo(ui: UI) -> None:
    """Draw the CYBERHEIST logo (the frame falls back to ASCII automatically)."""
    ui.box("", [ui.paint(line, "primary") for line in LOGO] + ["", ui.paint(SUBTITLE.center(58), "accent")])
    ui.say(TAGLINE.center(UI.WIDTH), "dim")


def briefing(ui: UI, m: Any, difficulty: str) -> None:
    """Mission briefing: story, objectives, difficulty, estimate, rewards, failure conditions."""
    lines = [m.intro, "", m.briefing, "", ui.paint("PRIMARY OBJECTIVES", "accent")]
    lines += [f"  - {o}" for o in m.primary]
    if m.optional:
        lines.append(ui.paint("OPTIONAL OBJECTIVES", "accent"))
        lines += [f"  - {o['text']} (+{o['xp']} XP, +{o['credits']} cr)" for o in m.optional]
    lines += ["", f"Tier: {m.tier}   Difficulty: {difficulty.upper()}   Est. ticks: {m.par_ticks}   "
                  f"Budget: {m.max_ticks}",
              f"Rewards: {m.reward_xp} XP, {m.reward_credits:,} cr",
              ui.paint("FAILURE CONDITIONS", "danger")]
    lines += [f"  - {f}" for f in m.failure]
    ui.box(f"MISSION {m.mid:02d}: {m.title.upper()}" if m.mid else m.title.upper(), lines)


def profile(ui: UI, player: Any, cfg: dict[str, Any], inventory: Any) -> None:
    """Hacker profile card."""
    prog = cfg["progression"]
    nxt = player.xp_to_next(prog["xp_thresholds"])
    gear = [inventory.cfg[i]["name"] for i in inventory.equipped()] or ["none"]
    ui.box(f"OPERATOR {player.alias}", [
        f"Rank: {player.level} {player.title(prog['level_titles'])}",
        f"XP: {player.xp:,}" + (f"  ({nxt:,} to next rank)" if nxt else "  (max rank)"),
        f"Credits: {player.credits:,}   Reputation: {player.reputation}",
        f"Missions completed: {player.missions_completed}/10",
        f"Infiltrations: {player.successes} successful, {player.failures} failed",
        f"Playtime: {player.play_ticks:.0f} ticks, {player.play_seconds / 60:.1f} min wall-clock",
        f"Equipped: {', '.join(gear)}",
        f"Last seed: {player.last_seed}",
    ])


def statistics(ui: UI, stats: Any) -> None:
    """Statistics dashboard."""
    ui.box("STATISTICS", [f"{label:<32} {value}" for label, value in stats.dashboard_rows()])


def achievements(ui: UI, tracker: Any, stats: Any) -> None:
    """Achievement list with progress."""
    rows = [(ui.paint(s, "ok" if s == "UNLOCKED" else "muted"), n, p, d) for s, n, p, d in tracker.rows(stats)]
    ui.table(["STATUS", "ACHIEVEMENT", "PROGRESS", "HOW"], rows)


def mission_database(ui: UI, missions: list[Any], progress: dict[int, dict[str, Any]]) -> None:
    """Table of missions with status and best results."""
    rows = []
    for m in missions:
        p = progress.get(m.mid, {"status": "locked"})
        best = f"{p['best_ticks']:.0f}" if p.get("best_ticks") is not None else "-"
        title = m.title if p["status"] != "locked" else "??????"
        rows.append((f"{m.mid:02d}", title, m.tier, p["status"].upper(), p.get("clears", 0), best))
    ui.table(["#", "MISSION", "TIER", "STATUS", "CLEARS", "BEST TICKS"], rows)


def network_map(ui: UI, netmap: Any) -> None:
    """ASCII topology: discovered nodes with links, plus a count of what is still unknown."""
    g = ui.theme.glyphs
    lines = []
    for node in sorted(netmap.discovered, key=lambda n: (n != "INTERNET", n)):
        links = sorted(netmap.neighbors(node) & netmap.discovered)
        mark = ui.paint(g["dot"], "warn" if node in netmap.hidden else "ok")
        tag = (" [hidden]" if node in netmap.hidden else " [target]" if node == netmap.target
               else " [locked]" if node in getattr(netmap, "locked", set()) else "")
        if node in netmap.hidden and node in getattr(netmap, "locked", set()):
            tag = " [hid,lck]"
        lines.append(f"{mark} {node:<9}{tag:<9} {g['arrow']} {', '.join(links) or '-'}")
    unknown = len(netmap.nodes - netmap.discovered)
    lines.append(ui.paint(f"{g['hollow']} {unknown} node(s) not yet discovered", "muted"))
    ui.box("NETWORK MAP", lines)


def completion(ui: UI, m: Any, result: Any, rewards: Any) -> None:
    """Mission complete summary with itemised rewards."""
    lines = [m.completion, "", f"Ticks: {result.ticks:.0f} (par {m.par_ticks})   "
                               f"Peak detection: {result.peak:.0f}%   Wrong guesses: {result.wrong}"]
    lines += [f"  {label:<40} +{xp:>4} XP  +{cr:>5,} cr" for label, xp, cr in rewards.lines]
    lines.append(f"  {'TOTAL':<40} +{rewards.xp:>4} XP  +{rewards.credits:>5,} cr")
    ui.box("MISSION COMPLETE", lines, role="ok")


def daily_board(ui: UI, rows: list[dict[str, Any]], today_seed: int, difficulty: str) -> None:
    """Your best daily-challenge scores, newest first."""
    if not rows:
        ui.info(f"No daily runs on {difficulty.upper()} yet. Today's seed: {today_seed}.")
        return
    table = []
    for r in rows:
        day = f"{str(r['seed'])[:4]}-{str(r['seed'])[4:6]}-{str(r['seed'])[6:]}"
        mark = " (today)" if r["seed"] == today_seed else ""
        table.append((day + mark, f"{r['best']:,}", f"{r['ticks']:.0f}", f"{r['peak']:.0f}%", r["plays"]))
    ui.say(f"DAILY BESTS ({difficulty.upper()})", "accent")
    ui.table(["DATE", "BEST", "TICKS", "PEAK", "PLAYS"], table)


def daily_score(ui: UI, breakdown: Any, best: int, new_best: bool) -> None:
    """Score card shown after a daily run."""
    lines = [f"  {label:<34} {value:+6d}" for label, value in breakdown.lines]
    lines += [f"  {'SCORE':<34} {breakdown.total:6d}", "",
              ui.paint("NEW PERSONAL BEST!", "ok") if new_best else f"Today's best stays at {best:,}."]
    ui.box("DAILY SCORE", lines, role="ok" if breakdown.total else "danger")


def game_over(ui: UI, m: Any, reason: str) -> None:
    """Mission failed screen."""
    ui.box("CONNECTION TERMINATED", [f"Mission {m.mid:02d}: {m.title}", "", reason, "",
                                     "Progress up to your last mission is safe. Try again from CONTINUE."],
           role="danger")


def stage_debrief(ui: UI, n: int, total: int, log: Any, facts: list[str], tips: list[str]) -> None:
    """Short report after a stage: cost, solver comparison, and the most useful tip."""
    outcome = "cleared" if log.cleared else "FAILED"
    head = (f"{outcome}  |  ticks {log.ticks:.0f}  |  detection {log.detection:+.0f}  |  "
            f"wrong {log.wrong}")
    lines = [ui.paint(head, "ok" if log.cleared else "danger")] + facts
    if tips:
        lines.append(ui.paint("TIP: " + tips[0], "warn"))
    ui.box(f"DEBRIEF: STAGE {n}/{total} {log.label.upper()}"[:60], lines, role="dim")


def run_summary(ui: UI, logs: list[Any], leak: Any, det: dict[str, Any]) -> None:
    """Table of every stage in the run, plus where most detection came from."""
    from systems.debrief import summarize
    ui.rule()
    ui.say("RUN SUMMARY", "accent")
    rows = [(i, log.label[:18], log.kind, "ok" if log.cleared else "FAILED", log.par_cell, log.wrong,
             f"{log.detection:+.0f}", f"{log.ticks:.0f}") for i, log in enumerate(logs, 1)]
    ui.table(["#", "STAGE", "TYPE", "RESULT", "VS PAR", "WRONG", "DET", "TICKS"], rows)
    if leak is not None:
        tips = summarize(leak, det)[1]
        ui.warn(f"Biggest leak: {leak.label} ({leak.detection:+.0f} detection).")
        for line in wrap(tips[0], UI.WIDTH - 4) if tips else []:
            ui.say("    " + line, "dim")
