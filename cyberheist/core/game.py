"""Top-level game: boot, registration, the main menu and every screen behind it."""
from __future__ import annotations

import datetime as dt
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from cyberheist.core.player import Player, validate_alias
from cyberheist.core.progression import compute_rewards
from cyberheist.core.rng import GameRNG
from cyberheist.core.state import MissionAborted, ScriptExhausted, Settings, load_config
from cyberheist.database.database import SaveManager
from cyberheist.interface import animations, screens
from cyberheist.interface.menus import Menu
from cyberheist.interface.theme import Theme
from cyberheist.interface.ui import UI, ConsoleIO, ScriptedIO
from cyberheist.missions.mission_runner import Mission, MissionContext, run_mission
from cyberheist.systems import adaptive
from cyberheist.systems.achievements import AchievementTracker, notify
from cyberheist.systems.daily import DAILY_KEY, DAILY_VERSION, build_daily, daily_seed, run_seed, score_run
from cyberheist.systems.black_market import BlackMarket
from cyberheist.systems.inventory import Inventory
from cyberheist.systems.statistics import Statistics

MAIN_OPTIONS = [
    ("new", "NEW GAME"), ("continue", "CONTINUE OPERATION"), ("database", "MISSION DATABASE"),
    ("market", "BLACK MARKET"), ("profile", "HACKER PROFILE"), ("achievements", "ACHIEVEMENTS"),
    ("settings", "SETTINGS"), ("exit", "EXIT"),
]


def load_campaign() -> tuple[list[Mission], list[str]]:
    """Load the campaign and any problems found while loading it.

    missions/mission_data.py wins if it exists. Otherwise the TOML mission files are read
    from cyberheist/missions/campaign/ and ~/.cyberheist/missions/ (see docs/mission-format.md).
    """
    try:
        from cyberheist.missions.mission_data import MISSIONS  # type: ignore[import-not-found]
    except ImportError:
        from cyberheist.missions.loader import BUNDLED_DIR, USER_DIR, load_dirs
        res = load_dirs(BUNDLED_DIR, USER_DIR)
        return res.missions, res.problems
    return list(MISSIONS), []


class Game:
    """Owns the save, the player state and the menu loop."""

    def __init__(self, io: ConsoleIO | ScriptedIO, save_path: Path | str, seed: int | None = None,
                 missions: list[Mission] | None = None, cfg: dict[str, Any] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 today: Callable[[], dt.date] = dt.date.today) -> None:
        """Create the game. Nothing touches disk until :meth:`run` or :meth:`load`."""
        self.io = io
        self.today = today
        self.cfg = cfg or load_config()
        self.rng = GameRNG(seed)
        self.save = SaveManager(save_path)
        self.missions, self.mission_problems = load_campaign() if missions is None else (list(missions), [])
        self.clock = clock
        self._last_clock = clock()
        self.player: Player | None = None
        self.settings = Settings(self.cfg["defaults"])
        self.inventory = Inventory(self.cfg["items"], self.cfg["max_equipped"])
        self.stats = Statistics()
        self.tracker = AchievementTracker()
        self.progress: dict[int, dict[str, Any]] = {}
        self.market = BlackMarket(self.cfg["items"])
        self.ui = self._build_ui()
        self.running = True

    # -- state & persistence ---------------------------------------------------------
    def _build_ui(self) -> UI:
        s = self.settings
        return UI(self.io, Theme(s.get("theme")), typewriter=s.get("typewriter"),
                  speed=s.get("animation_speed"), animations=s.get("animations"), sound=s.get("sound"))

    def load(self) -> None:
        """Open the save (quarantining a corrupt one) and restore all state."""
        report = self.save.open()
        self.settings = Settings(self.cfg["defaults"], self.save.load_settings())
        self.ui = self._build_ui()
        if report.corrupt_backup is not None:
            self.ui.error(f"Save file was damaged ({report.reason}).")
            self.ui.warn(f"It was moved to {report.corrupt_backup.name}. Starting a fresh profile.")
        self.player = self.save.load_profile()
        if self.player:
            self.player.refresh_level(self.cfg["progression"]["xp_thresholds"])
        self.inventory = Inventory(self.cfg["items"], self.cfg["max_equipped"], self.save.load_inventory())
        self.stats = Statistics(self.save.load_statistics())
        self.tracker = AchievementTracker(self.save.load_achievements())
        self.progress = self.save.load_missions()
        self._ensure_progress()

    def _ensure_progress(self) -> None:
        for i, m in enumerate(self.missions):
            self.progress.setdefault(m.mid, {"status": "available" if i == 0 else "locked", "attempts": 0,
                                             "clears": 0, "best_ticks": None, "best_detection": None,
                                             "optional_done": [], "checkpoint": None})

    def persist(self) -> None:
        """Save everything in one transaction, adding wall-clock playtime since the last save."""
        if self.save.conn is None:
            return
        now = self.clock()
        if self.player:
            self.player.play_seconds += max(0.0, now - self._last_clock)
        self._last_clock = now
        self.save.save_all(self.player, self.progress, self.inventory.to_rows(), self.tracker.to_rows(),
                           self.settings.as_dict(), self.stats.to_rows())

    # -- entry point -----------------------------------------------------------------
    def run(self) -> None:
        """Boot, register if needed, then loop the main menu until EXIT."""
        try:
            self.load()
            animations.boot_sequence(self.ui, self.cfg["ui"]["boot_seconds"])
            screens.logo(self.ui)
            self._size_check()
            if self.player is None:
                self.register()
            else:
                self.ui.ok(f"Welcome back, {self.player.alias}.")
            while self.running:
                self._guarded(self.main_menu)
        except (KeyboardInterrupt, EOFError) as exc:
            self.ui.blank()
            self.ui.warn(("Input closed" if isinstance(exc, EOFError) else "Interrupt received")
                         + ". Saving progress...")
            self.persist()
            self.ui.ok("Saved. Disconnecting.")
        finally:
            self.save.close()

    def _guarded(self, fn: Callable[[], None]) -> None:
        """Run one menu action; any unexpected error is reported, saved past, and the loop continues."""
        try:
            fn()
        except (KeyboardInterrupt, EOFError, ScriptExhausted):
            raise
        except Exception as exc:  # loop boundary: never crash on bad input
            self.ui.error(f"Something glitched: {exc.__class__.__name__}: {exc}")
            self.ui.info(f"Your progress is safe. Include seed {self.rng.seed} in a bug report.")
            self.persist()

    def _size_check(self) -> None:
        size = shutil.get_terminal_size((80, 24))
        need_w, need_h = self.cfg["ui"]["min_width"], self.cfg["ui"]["min_height"]
        if size.columns < need_w or size.lines < need_h:
            self.ui.warn(f"Terminal is {size.columns}x{size.lines}; {need_w}x{need_h} or larger is recommended.")

    def register(self) -> None:
        """Create a new hacker identity."""
        self.ui.box("IDENTITY REGISTRATION", ["Choose an alias: 3-16 characters, letters, digits, '_' or '-'."])
        while True:
            alias = self.ui.prompt("alias")
            err = validate_alias(alias)
            if err is None:
                break
            self.ui.warn(err)
        self.player = Player(alias=alias.strip(), credits=self.cfg["progression"]["starting_credits"],
                             created_at=time.strftime("%Y-%m-%d %H:%M"))
        self.persist()
        self.ui.ok(f"Identity {self.player.alias} registered. {self.player.credits:,} cr loaded.")

    # -- main menu -----------------------------------------------------------------
    def main_menu(self) -> None:
        """Show the main menu once and run the chosen option."""
        choice = Menu("MAIN MENU", MAIN_OPTIONS, allow_back=False).choose(self.ui)
        {"new": self.new_game, "continue": self.continue_operation, "database": self.mission_database,
         "market": self.black_market, "profile": self.hacker_profile, "achievements": self.achievements,
         "settings": self.settings_menu, "exit": self.exit}[choice or "exit"]()

    def new_game(self) -> None:
        """Start over with a new identity (after confirmation if progress exists)."""
        if self.player and (self.player.xp or self.player.missions_completed or self.inventory.rows):
            if not self.ui.confirm(f"Erase {self.player.alias}'s progress and start over?"):
                self.ui.info("Kept your current profile.")
                return
        self.save.wipe_progress()
        self.player = None
        self.inventory = Inventory(self.cfg["items"], self.cfg["max_equipped"])
        self.stats, self.tracker, self.progress = Statistics(), AchievementTracker(), {}
        self._ensure_progress()
        self.register()
        if self.missions:
            self.play(self.missions[0])

    def continue_operation(self) -> None:
        """Resume a checkpoint, or start the next unlocked mission."""
        if not self.missions:
            self.ui.warn("No missions are installed (missions/mission_data.py is missing).")
            return
        for m in self.missions:
            cp = self.progress[m.mid].get("checkpoint")
            if cp and self.ui.confirm(f"Resume {m.title} from stage {cp['stage'] + 1}?"):
                self.play(m, checkpoint=cp)
                return
        for m in self.missions:
            if self.progress[m.mid]["status"] == "available":
                self.play(m)
                return
        self.ui.ok("Campaign complete. Replay any mission from the MISSION DATABASE.")

    def mission_database(self) -> None:
        """List missions and today's daily challenge; pick one to brief and play."""
        while True:
            if self.missions:
                screens.mission_database(self.ui, self.missions, self.progress)
            else:
                from cyberheist.missions.loader import FORMAT_URL, USER_DIR
                self.ui.warn(f"No missions are installed. Add mission files to {USER_DIR}.")
                self.ui.info(f"Format: {FORMAT_URL}")
            if self.mission_problems:
                self.ui.warn(f"{len(self.mission_problems)} problem(s) in mission files kept some out. "
                             "Run 'cyberheist --check-missions' for details.")
            difficulty = self.settings.get("difficulty")
            screens.daily_board(self.ui, self.save.load_scores(f"{DAILY_KEY}-{difficulty}"),
                                daily_seed(self.today()), difficulty)
            raw = self.ui.prompt("mission #, d = daily challenge, b = back")
            if raw.lower() in ("b", "back", ""):
                return
            if raw.lower() == "d":
                self.play_daily()
                return
            if raw == "?":
                self.ui.info("Type a mission number to see its briefing and play it, or 'd' for the "
                             "daily challenge: the same run for everyone today, best score kept.")
                continue
            m = next((x for x in self.missions if raw.isdigit() and x.mid == int(raw)), None)
            if m is None:
                self.ui.warn("No mission with that number.")
            elif self.progress[m.mid]["status"] == "locked":
                self.ui.warn("Locked. Clear the previous mission first.")
            else:
                self.play(m)
                return

    def black_market(self) -> None:
        """Buy, equip and unequip gear."""
        help_text = "Commands: buy N, equip N, unequip N, b. Max 2 passives equipped."
        while True:
            self.ui.box("BLACK MARKET", [f"Credits: {self.player.credits:,}", help_text])
            rows = [r[:6] for r in self.market.listing(self.inventory)]
            self.ui.table(["#", "ITEM", "PRICE", "KIND", "USES", "OWNED"], rows)
            raw = self.ui.prompt("market")
            verb, _, arg = raw.lower().partition(" ")
            if verb in ("b", "back", ""):
                return
            if verb == "?":
                self.ui.info(help_text)
                for _, name, _, _, _, _, desc in self.market.listing(self.inventory):
                    self.ui.say(f"  {name}: {desc}")
                continue
            iid = self.market.resolve(arg)
            if verb not in ("buy", "equip", "unequip") or iid is None:
                self.ui.warn(help_text)
                continue
            if verb == "buy":
                ok, msg = self.market.buy(self.player, self.inventory, iid)
                if ok:
                    self.stats.bump("items_bought")
                    self._achievements()
            elif verb == "equip":
                ok, msg = self.inventory.equip(iid)
            else:
                ok, msg = self.inventory.unequip(iid)
            (self.ui.ok if ok else self.ui.warn)(msg)
            if ok:
                self.persist()

    def hacker_profile(self) -> None:
        """Profile card and statistics dashboard, with a manual save."""
        screens.profile(self.ui, self.player, self.cfg, self.inventory)
        screens.statistics(self.ui, self.stats)
        while True:
            raw = self.ui.prompt("profile (s = save now, b = back)").lower()
            if raw == "s":
                self.persist()
                self.ui.ok("Game saved.")
            elif raw in ("b", "back", ""):
                return
            else:
                self.ui.info("Type 's' to save now or 'b' to go back.")

    def achievements(self) -> None:
        """Achievement list."""
        screens.achievements(self.ui, self.tracker, self.stats)
        self.ui.wait()

    def settings_menu(self) -> None:
        """Change settings; each change is saved immediately."""
        cycles = {"difficulty": ["easy", "normal", "hard"], "theme": ["green", "amber", "cyan"],
                  "animation_speed": [0.5, 1.0, 2.0]}
        while True:
            s = self.settings
            opts = [(k, f"{k.replace('_', ' ').title():<16} {s.get(k)}") for k in Settings.KEYS]
            opts.append(("reset", "Reset to defaults"))
            key = Menu("SETTINGS", opts, "Pick a setting to change it.").choose(self.ui)
            if key is None:
                return
            if key == "reset":
                s.reset()
            elif key in cycles:
                vals = cycles[key]
                cur = s.get(key)
                s.set(key, vals[(vals.index(cur) + 1) % len(vals)] if cur in vals else vals[0])
            else:
                s.set(key, not s.get(key))
            self.ui = self._build_ui()
            self.persist()
            self.ui.ok("Setting saved.")

    def exit(self) -> None:
        """Save and leave."""
        self.persist()
        self.ui.ok("Progress saved. Stay invisible.")
        self.running = False

    # -- missions ------------------------------------------------------------------
    def play(self, m: Mission, checkpoint: dict[str, Any] | None = None) -> None:
        """Brief, run and settle one mission."""
        p = self.progress[m.mid]
        difficulty = self.settings.get("difficulty")
        screens.briefing(self.ui, m, difficulty)
        if not self.ui.confirm("Begin infiltration?", lambda: "y"):
            self.ui.info("Mission postponed.")
            return
        seed = int(checkpoint["seed"]) if checkpoint else self.rng.fork(f"m{m.mid}-{p['attempts']}").seed
        self.player.last_seed = seed

        def between(ctx: MissionContext, n: int) -> None:
            p["checkpoint"] = {"stage": n + 1, "ticks": ctx.ticks, "detection": ctx.meter.level,
                               "peak": ctx.meter.peak, "wrong": ctx.wrong_guesses, "seed": seed}
            self.persist()
            self._stage_break()

        result = run_mission(self.ui, GameRNG(seed), self.cfg, m, difficulty, self.inventory, checkpoint, between,
                             debrief=self.settings.get("debrief"))
        self._settle(m, result, difficulty)

    def _stage_break(self) -> None:
        raw = self.ui.prompt("stage clear: ENTER to continue, P to pause", lambda: "")
        if raw.lower() != "p":
            return
        choice = Menu("PAUSED", [("resume", "Resume mission"), ("abort", "Abort mission (counts as failed)")],
                      allow_back=False).choose(self.ui)
        if choice == "abort":
            raise MissionAborted()

    def _settle(self, m: Mission, r: Any, difficulty: str) -> None:
        prog = self.cfg["progression"]
        p = self.progress[m.mid]
        pl = self.player
        p["attempts"] = p.get("attempts", 0) + 1
        p["checkpoint"] = None
        pl.play_ticks += r.ticks
        speed = r.success and r.ticks < m.par_ticks
        if r.success:
            first = p["status"] != "completed"
            rewards = compute_rewards(m, r.optional_done, r.ghost, speed, r.bonus_credits, prog,
                                      self.cfg["difficulty"][difficulty]["reward_mult"], replay=not first)
            leveled = pl.add_xp(rewards.xp, prog["xp_thresholds"])
            pl.add_credits(rewards.credits)
            pl.adjust_reputation(prog["reputation_success"] + prog["reputation_optional"] * len(r.optional_done))
            pl.record_success(first)
            p["status"] = "completed"
            p["clears"] = p.get("clears", 0) + 1
            p["best_ticks"] = r.ticks if p.get("best_ticks") is None else min(p["best_ticks"], r.ticks)
            p["best_detection"] = r.peak if p.get("best_detection") is None else min(p["best_detection"], r.peak)
            p["optional_done"] = sorted(set(p.get("optional_done", [])) | set(r.optional_done))
            idx = [x.mid for x in self.missions].index(m.mid)
            if idx + 1 < len(self.missions):
                nxt = self.progress[self.missions[idx + 1].mid]
                if nxt["status"] == "locked":
                    nxt["status"] = "available"
            self.ui.alert()
            screens.completion(self.ui, m, r, rewards)
            if leveled:
                self.ui.ok(f"RANK UP: {pl.level} {pl.title(prog['level_titles'])}")
            credits = rewards.credits
        else:
            pl.record_failure()
            pl.adjust_reputation(prog["reputation_fail"])
            self.ui.alert()
            screens.game_over(self.ui, m, r.reason)
            credits = 0
        self.stats.record_mission(m.mid, r.success, r.ticks, m.par_ticks, r.peak, r.wrong, r.solved,
                                  len(r.items_used), credits)
        self._adapt()
        self._achievements()
        self.persist()
        self.ui.wait()

    def play_daily(self) -> None:
        """Play today's daily challenge and keep the best score per day and difficulty."""
        day = self.today()
        seed = run_seed(day)
        m = build_daily(day)
        difficulty = self.settings.get("difficulty")
        screens.briefing(self.ui, m, difficulty)
        self.ui.info(f"Seed {seed} (puzzle version {DAILY_VERSION}). Everyone on {difficulty.upper()} "
                     "gets this exact run today.")
        if not self.ui.confirm("Begin the daily run?", lambda: "y"):
            self.ui.info("Daily run postponed.")
            return
        self.player.last_seed = seed

        def between(ctx: MissionContext, n: int) -> None:
            self._stage_break()

        r = run_mission(self.ui, GameRNG(seed), self.cfg, m, difficulty, self.inventory, None, between,
                        debrief=self.settings.get("debrief"))
        if not r.success:
            screens.game_over(self.ui, m, r.reason)
        breakdown = score_run(r, m.par_ticks)
        best, new_best = self.save.record_score(f"{DAILY_KEY}-{difficulty}", daily_seed(day), breakdown.total,
                                                r.ticks, r.peak, day.isoformat())
        screens.daily_score(self.ui, breakdown, best, new_best)
        pl = self.player
        pl.play_ticks += r.ticks
        credits = breakdown.total // 10
        if r.success:
            leveled = pl.add_xp(breakdown.total // 20, self.cfg["progression"]["xp_thresholds"])
            pl.add_credits(credits)
            self.ui.ok(f"Payout: +{breakdown.total // 20} XP, +{credits:,} cr.")
            if leveled:
                self.ui.ok(f"RANK UP: {pl.level} {pl.title(self.cfg['progression']['level_titles'])}")
        self.stats.bump("daily_runs")
        self.stats.values["daily_best"] = max(self.stats["daily_best"], breakdown.total)
        self.stats.record_mission(0, r.success, r.ticks, m.par_ticks, r.peak, r.wrong, r.solved,
                                  len(r.items_used), credits if r.success else 0)
        self.ui.alert()
        self._adapt()
        self._achievements()
        self.persist()
        self.ui.wait()

    def _adapt(self) -> None:
        """With adaptive difficulty on, step the setting after repeated failures or clean wins."""
        if not self.settings.get("adaptive"):
            return
        current = self.settings.get("difficulty")
        new = adaptive.suggest(current, self.stats)
        if new is None:
            return
        self.settings.set("difficulty", new)
        self.stats.values["fail_streak"] = 0
        self.stats.values["clean_streak"] = 0
        direction = "down" if adaptive.ORDER.index(new) < adaptive.ORDER.index(current) else "up"
        self.ui.info(f"Adaptive difficulty: stepping {direction} to {new.upper()}.")

    def _achievements(self) -> None:
        new = self.tracker.evaluate(self.stats)
        if new:
            notify(self.ui, new)
            self.persist()
