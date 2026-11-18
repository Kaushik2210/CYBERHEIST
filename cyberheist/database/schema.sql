-- CYBERHEIST save schema, version 1. Later versions are applied as migrations
-- in database/database.py.
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    alias TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    credits INTEGER NOT NULL DEFAULT 0,
    reputation INTEGER NOT NULL DEFAULT 0,
    missions_completed INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    play_ticks REAL NOT NULL DEFAULT 0,
    play_seconds REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mission_progress (
    mission_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'locked',
    attempts INTEGER NOT NULL DEFAULT 0,
    clears INTEGER NOT NULL DEFAULT 0,
    best_ticks REAL,
    best_detection REAL,
    optional_done TEXT NOT NULL DEFAULT '[]',
    checkpoint TEXT
);

CREATE TABLE IF NOT EXISTS inventory (
    item_id TEXT PRIMARY KEY,
    uses INTEGER NOT NULL DEFAULT 0,
    equipped INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS achievements (
    achievement_id TEXT PRIMARY KEY,
    unlocked_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS statistics (
    key TEXT PRIMARY KEY,
    value REAL NOT NULL DEFAULT 0
);
