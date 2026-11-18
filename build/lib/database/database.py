"""SQLite save manager: migrations, transactions and corruption recovery."""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from core.player import Player

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# version -> SQL applied to reach that version. Version 1 is schema.sql.
MIGRATIONS: dict[int, str] = {
    2: "ALTER TABLE profile ADD COLUMN last_seed INTEGER NOT NULL DEFAULT 0;",
    3: """CREATE TABLE IF NOT EXISTS scores (
              run_key TEXT NOT NULL,
              seed INTEGER NOT NULL,
              best INTEGER NOT NULL,
              ticks REAL NOT NULL,
              peak REAL NOT NULL,
              played_on TEXT NOT NULL,
              plays INTEGER NOT NULL DEFAULT 1,
              PRIMARY KEY (run_key, seed)
          );""",
}
LATEST_VERSION = max(MIGRATIONS) if MIGRATIONS else 1
MISSION_STATUSES = ("locked", "available", "completed")


class SaveCorrupted(Exception):
    """The save file failed an integrity or range check."""


@dataclass
class LoadReport:
    """What happened while opening the save."""

    created: bool = False
    corrupt_backup: Path | None = None
    reason: str = ""
    migrated_from: int | None = None


class SaveManager:
    """Owns the SQLite connection for one save file."""

    def __init__(self, path: Path | str) -> None:
        """Remember the path; call :meth:`open` to connect."""
        self.path = Path(path)
        self.conn: sqlite3.Connection | None = None

    # -- lifecycle -------------------------------------------------------------
    def open(self) -> LoadReport:
        """Open (creating or migrating) the save. Corrupt files are quarantined, never overwritten."""
        report = LoadReport()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists() and self.path.stat().st_size > 0
        if existed:
            try:
                self._connect()
                report.migrated_from = self._migrate()
                self.validate()
                return report
            except (sqlite3.DatabaseError, SaveCorrupted, ValueError, TypeError, json.JSONDecodeError) as exc:
                self.close()
                report.reason = str(exc) or exc.__class__.__name__
                report.corrupt_backup = self._quarantine()
        self._connect()
        self._migrate()
        report.created = True
        return report

    def _connect(self) -> None:
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        """Close the connection if open."""
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def _quarantine(self) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}{self.path.suffix}")
        n = 1
        while target.exists():
            target = self.path.with_name(f"{self.path.stem}.corrupt-{stamp}-{n}{self.path.suffix}")
            n += 1
        shutil.move(str(self.path), str(target))
        return target

    def reset_file(self) -> Path | None:
        """Move the current save aside (``.reset-<ts>``) and start a fresh one."""
        self.close()
        backup = None
        if self.path.exists():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"{self.path.stem}.reset-{stamp}{self.path.suffix}")
            shutil.move(str(self.path), str(backup))
        self.open()
        return backup

    # -- schema --------------------------------------------------------------
    def version(self) -> int:
        """Current schema version (0 if the table is missing/empty)."""
        assert self.conn is not None
        try:
            row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row[0]) if row else 0

    def _migrate(self) -> int | None:
        """Bring the schema up to date. Returns the starting version if it changed."""
        assert self.conn is not None
        start = self.version()
        if start > LATEST_VERSION:
            raise SaveCorrupted(f"save is from a newer version ({start})")
        if start == LATEST_VERSION:
            return None
        with self.transaction():
            if start == 0:
                for stmt in _split_sql(SCHEMA_PATH.read_text(encoding="utf-8")):
                    self.conn.execute(stmt)
                self.conn.execute("DELETE FROM schema_version")
                self.conn.execute("INSERT INTO schema_version(version) VALUES (1)")
                current = 1
            else:
                current = start
            for version in sorted(MIGRATIONS):
                if version > current:
                    for stmt in _split_sql(MIGRATIONS[version]):
                        self.conn.execute(stmt)
                    self.conn.execute("UPDATE schema_version SET version = ?", (version,))
                    current = version
        return start

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block atomically: commit on success, roll back on any exception."""
        assert self.conn is not None, "save not open"
        self.conn.execute("BEGIN")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def validate(self) -> None:
        """Run ``PRAGMA integrity_check`` plus value range checks. Raises SaveCorrupted."""
        assert self.conn is not None
        result = self.conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SaveCorrupted(f"integrity check failed: {result}")
        row = self.conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        if row is not None:
            checks = [
                (1 <= row["level"] <= 8, "level"), (row["xp"] >= 0, "xp"), (row["credits"] >= 0, "credits"),
                (0 <= row["reputation"] <= 1000, "reputation"), (row["missions_completed"] >= 0, "missions"),
                (row["successes"] >= 0, "successes"), (row["failures"] >= 0, "failures"),
                (row["play_ticks"] >= 0 and row["play_seconds"] >= 0, "playtime"),
                (isinstance(row["alias"], str) and 3 <= len(row["alias"]) <= 16, "alias"),
            ]
            for ok, name in checks:
                if not ok:
                    raise SaveCorrupted(f"profile value out of range: {name}")
        for r in self.conn.execute("SELECT * FROM mission_progress"):
            if r["status"] not in MISSION_STATUSES or not (1 <= r["mission_id"] <= 10) or r["attempts"] < 0:
                raise SaveCorrupted(f"bad mission row {r['mission_id']}")
            json.loads(r["optional_done"])
            if r["checkpoint"]:
                json.loads(r["checkpoint"])
        for r in self.conn.execute("SELECT * FROM inventory"):
            if r["uses"] < 0 or r["equipped"] not in (0, 1):
                raise SaveCorrupted(f"bad inventory row {r['item_id']}")
        for r in self.conn.execute("SELECT value FROM settings"):
            json.loads(r["value"])
        for r in self.conn.execute("SELECT * FROM scores"):
            if r["best"] < 0 or r["ticks"] < 0 or not (0 <= r["peak"] <= 100) or r["plays"] < 1:
                raise SaveCorrupted(f"bad score row {r['run_key']}/{r['seed']}")

    # -- profile ---------------------------------------------------------------
    def load_profile(self) -> Player | None:
        """Return the saved player or None."""
        assert self.conn is not None
        row = self.conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        return Player.from_dict(dict(row)) if row else None

    def _write_profile(self, conn: sqlite3.Connection, p: Player) -> None:
        conn.execute(
            """INSERT INTO profile(id, alias, level, xp, credits, reputation, missions_completed, successes,
                   failures, play_ticks, play_seconds, created_at, last_seed)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET alias=excluded.alias, level=excluded.level, xp=excluded.xp,
                   credits=excluded.credits, reputation=excluded.reputation,
                   missions_completed=excluded.missions_completed, successes=excluded.successes,
                   failures=excluded.failures, play_ticks=excluded.play_ticks,
                   play_seconds=excluded.play_seconds, created_at=excluded.created_at,
                   last_seed=excluded.last_seed""",
            (p.alias, p.level, p.xp, p.credits, p.reputation, p.missions_completed, p.successes,
             p.failures, p.play_ticks, p.play_seconds, p.created_at, p.last_seed),
        )

    def save_profile(self, p: Player) -> None:
        """Save only the profile."""
        with self.transaction() as conn:
            self._write_profile(conn, p)

    # -- other tables ----------------------------------------------------------
    def load_missions(self) -> dict[int, dict[str, Any]]:
        """Return mission progress rows keyed by id."""
        assert self.conn is not None
        out: dict[int, dict[str, Any]] = {}
        for r in self.conn.execute("SELECT * FROM mission_progress"):
            d = dict(r)
            d["optional_done"] = json.loads(d["optional_done"])
            d["checkpoint"] = json.loads(d["checkpoint"]) if d["checkpoint"] else None
            out[d["mission_id"]] = d
        return out

    def load_inventory(self) -> dict[str, dict[str, int]]:
        """Return inventory rows keyed by item id."""
        assert self.conn is not None
        return {r["item_id"]: {"uses": r["uses"], "equipped": r["equipped"]}
                for r in self.conn.execute("SELECT * FROM inventory")}

    def load_achievements(self) -> dict[str, str]:
        """Return unlocked achievement ids -> timestamp."""
        assert self.conn is not None
        return {r["achievement_id"]: r["unlocked_at"] for r in self.conn.execute("SELECT * FROM achievements")}

    def load_settings(self) -> dict[str, Any]:
        """Return stored setting overrides."""
        assert self.conn is not None
        return {r["key"]: json.loads(r["value"]) for r in self.conn.execute("SELECT * FROM settings")}

    def load_statistics(self) -> dict[str, float]:
        """Return statistics counters."""
        assert self.conn is not None
        return {r["key"]: r["value"] for r in self.conn.execute("SELECT * FROM statistics")}

    def save_all(self, player: Player | None, missions: dict[int, dict[str, Any]],
                 inventory: dict[str, dict[str, int]], achievements: dict[str, str],
                 settings: dict[str, Any], statistics: dict[str, float]) -> None:
        """Write the whole game state in a single transaction."""
        with self.transaction() as conn:
            if player is not None:
                self._write_profile(conn, player)
            conn.execute("DELETE FROM mission_progress")
            for mid, m in missions.items():
                conn.execute(
                    "INSERT INTO mission_progress VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (mid, m["status"], m.get("attempts", 0), m.get("clears", 0), m.get("best_ticks"),
                     m.get("best_detection"), json.dumps(m.get("optional_done", [])),
                     json.dumps(m["checkpoint"]) if m.get("checkpoint") else None),
                )
            conn.execute("DELETE FROM inventory")
            for iid, row in inventory.items():
                conn.execute("INSERT INTO inventory VALUES (?, ?, ?)", (iid, int(row["uses"]), int(bool(row["equipped"]))))
            conn.execute("DELETE FROM achievements")
            for aid, ts in achievements.items():
                conn.execute("INSERT INTO achievements VALUES (?, ?)", (aid, ts))
            conn.execute("DELETE FROM settings")
            for k, v in settings.items():
                conn.execute("INSERT INTO settings VALUES (?, ?)", (k, json.dumps(v)))
            conn.execute("DELETE FROM statistics")
            for k, v in statistics.items():
                conn.execute("INSERT INTO statistics VALUES (?, ?)", (k, float(v)))

    # -- scores ----------------------------------------------------------------
    def record_score(self, run_key: str, seed: int, score: int, ticks: float, peak: float,
                     played_on: str) -> tuple[int, bool]:
        """Store a run's score, keeping the best per (run_key, seed).

        Returns (best score now on record, whether this run set a new best).
        """
        assert self.conn is not None
        with self.transaction() as conn:
            row = conn.execute("SELECT best, plays FROM scores WHERE run_key = ? AND seed = ?",
                               (run_key, seed)).fetchone()
            if row is None:
                conn.execute("INSERT INTO scores VALUES (?, ?, ?, ?, ?, ?, 1)",
                             (run_key, seed, score, ticks, peak, played_on))
                return score, True
            if score > row["best"]:
                conn.execute("UPDATE scores SET best = ?, ticks = ?, peak = ?, played_on = ?, plays = plays + 1 "
                             "WHERE run_key = ? AND seed = ?", (score, ticks, peak, played_on, run_key, seed))
                return score, True
            conn.execute("UPDATE scores SET plays = plays + 1 WHERE run_key = ? AND seed = ?", (run_key, seed))
            return row["best"], False

    def load_scores(self, run_key: str, limit: int = 7) -> list[dict[str, Any]]:
        """Most recent best scores for a run type, newest seed first."""
        assert self.conn is not None
        rows = self.conn.execute("SELECT * FROM scores WHERE run_key = ? ORDER BY seed DESC LIMIT ?",
                                 (run_key, limit))
        return [dict(r) for r in rows]

    def wipe_progress(self) -> None:
        """Delete profile and progress (settings are kept)."""
        with self.transaction() as conn:
            for table in ("profile", "mission_progress", "inventory", "achievements", "statistics", "scores"):
                conn.execute(f"DELETE FROM {table}")


def _split_sql(script: str) -> list[str]:
    """Split a SQL script into statements, dropping comments."""
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
