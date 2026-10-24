-- Safe to run on every startup: tables are only created if missing.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    gender TEXT NOT NULL,
    major TEXT NOT NULL,
    year TEXT NOT NULL,
    courses TEXT NOT NULL DEFAULT '',         -- comma-separated, e.g. "CHEM 1315, MATH 1914"
    cc INTEGER NOT NULL DEFAULT 0,            -- Crimson Crystals available to spend
    cc_earned INTEGER NOT NULL DEFAULT 0,     -- all-time CC earned (leaderboards use this)
    xp INTEGER NOT NULL DEFAULT 0,            -- level is calculated from this
    study_minutes INTEGER NOT NULL DEFAULT 0,
    raids INTEGER NOT NULL DEFAULT 0,         -- campus events attended (OU Engage, coming soon)
    skin TEXT NOT NULL DEFAULT '#e8b48a',
    outfit TEXT NOT NULL DEFAULT '{}'         -- JSON {slot: item_id} of equipped avatar items
);

CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,                    -- key into avatar.ITEMS
    PRIMARY KEY (user_id, item_id)
);

-- One row per direction: a friend request is a single row, friends have both.
CREATE TABLE IF NOT EXISTS friendships (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, friend_id)
);

CREATE TABLE IF NOT EXISTS parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leader_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    course TEXT NOT NULL,
    dungeon TEXT NOT NULL,                    -- key into DUNGEONS in app.py
    spot TEXT NOT NULL DEFAULT '',            -- room number, floor, table...
    description TEXT NOT NULL DEFAULT '',
    capacity INTEGER NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS party_members (
    party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (party_id, user_id)
);

-- A study session in a dungeon. ended_at is NULL while it's running.
CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dungeon TEXT NOT NULL,
    party_id INTEGER REFERENCES parties(id) ON DELETE SET NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    minutes INTEGER NOT NULL DEFAULT 0,
    cc INTEGER NOT NULL DEFAULT 0,
    xp INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind TEXT NOT NULL,                       -- Club, Fraternity, Sorority, ...
    emblem TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    founder_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS clan_members (
    clan_id INTEGER NOT NULL REFERENCES clans(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (clan_id, user_id)
);
