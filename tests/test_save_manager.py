"""Save manager: round trips, corruption handling, migrations and transaction rollback."""
import sqlite3

import pytest

from core.player import Player
from database.database import LATEST_VERSION, SCHEMA_PATH, SaveManager, SaveCorrupted, _split_sql


def open_save(path):
    sm = SaveManager(path)
    report = sm.open()
    return sm, report


def test_full_round_trip(tmp_path):
    sm, report = open_save(tmp_path / "s.db")
    assert report.created and sm.version() == LATEST_VERSION
    p = Player(alias="Neo_01", xp=900, credits=4321, reputation=40, missions_completed=2, last_seed=77)
    missions = {1: {"status": "completed", "attempts": 2, "clears": 1, "best_ticks": 12.0, "best_detection": 8.0,
                    "optional_done": ["tidy"], "checkpoint": None},
                2: {"status": "available", "attempts": 1, "clears": 0, "best_ticks": None, "best_detection": None,
                    "optional_done": [], "checkpoint": {"stage": 1, "seed": 9}}}
    inv = {"ghost_proxy": {"uses": 1, "equipped": 1}, "cipher_toolkit": {"uses": 4, "equipped": 0}}
    sm.save_all(p, missions, inv, {"first_breach": "2026-11-18"}, {"theme": "amber"}, {"missions_won": 3.0})
    sm.close()
    sm2, report2 = open_save(tmp_path / "s.db")
    assert not report2.created and report2.corrupt_backup is None
    assert sm2.load_profile().to_dict() == p.to_dict()
    assert sm2.load_missions() == {k: {**v, "mission_id": k} for k, v in missions.items()}
    assert sm2.load_inventory() == inv
    assert sm2.load_achievements() == {"first_breach": "2026-11-18"}
    assert sm2.load_settings() == {"theme": "amber"}
    assert sm2.load_statistics() == {"missions_won": 3.0}
    sm2.close()


def test_garbage_file_is_quarantined_not_overwritten(tmp_path):
    path = tmp_path / "save.db"
    path.write_bytes(b"not sqlite" * 300)
    sm, report = open_save(path)
    assert report.corrupt_backup is not None and report.corrupt_backup.read_bytes() == b"not sqlite" * 300
    assert report.created and sm.load_profile() is None
    sm.close()


def test_out_of_range_values_are_treated_as_corruption(tmp_path):
    path = tmp_path / "save.db"
    sm, _ = open_save(path)
    sm.save_profile(Player(alias="Neo_01"))
    sm.conn.execute("UPDATE profile SET credits = -50")
    sm.close()
    sm2, report = open_save(path)
    assert report.corrupt_backup is not None and "credits" in report.reason
    sm2.close()


def test_migrates_a_version_1_save_and_keeps_the_profile(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for stmt in _split_sql(SCHEMA_PATH.read_text(encoding="utf-8")):
        conn.execute(stmt)
    conn.execute("INSERT INTO schema_version VALUES (1)")
    conn.execute("INSERT INTO profile(id, alias, xp, credits) VALUES (1, 'Oldie', 500, 1500)")
    conn.commit()
    conn.close()
    sm, report = open_save(path)
    assert report.migrated_from == 1 and sm.version() == LATEST_VERSION == 3
    p = sm.load_profile()
    assert p.alias == "Oldie" and p.credits == 1500 and p.last_seed == 0      # column added by v2
    assert sm.record_score("daily-normal", 1, 10, 1, 1, "d") == (10, True)    # table added by v3
    sm.close()


def test_newer_save_version_is_refused_safely(tmp_path):
    path = tmp_path / "s.db"
    sm, _ = open_save(path)
    sm.conn.execute("UPDATE schema_version SET version = 99")
    sm.close()
    sm2, report = open_save(path)
    assert report.corrupt_backup is not None and "newer version" in report.reason
    sm2.close()


def test_transaction_rolls_back_on_error(tmp_path):
    sm, _ = open_save(tmp_path / "s.db")
    sm.save_profile(Player(alias="Before", credits=10))
    with pytest.raises(RuntimeError):
        with sm.transaction() as conn:
            conn.execute("UPDATE profile SET alias = 'During', credits = 999")
            raise RuntimeError("crash mid-save")
    p = sm.load_profile()
    assert p.alias == "Before" and p.credits == 10
    sm.close()


def test_reset_moves_the_old_save_aside(tmp_path):
    path = tmp_path / "s.db"
    sm, _ = open_save(path)
    sm.save_profile(Player(alias="Keepme"))
    backup = sm.reset_file()
    assert backup is not None and backup.exists() and sm.load_profile() is None
    sm.close()
    old = SaveManager(backup)
    old.open()
    assert old.load_profile().alias == "Keepme"
    old.close()


def test_validate_raises_on_bad_mission_rows(tmp_path):
    sm, _ = open_save(tmp_path / "s.db")
    sm.conn.execute("INSERT INTO mission_progress(mission_id, status) VALUES (3, 'weird')")
    with pytest.raises(SaveCorrupted):
        sm.validate()
    sm.close()
