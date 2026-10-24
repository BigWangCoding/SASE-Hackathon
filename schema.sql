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
    outfit TEXT NOT NULL DEFAULT '{}',        -- JSON {slot: item_id} of equipped avatar items
    role TEXT NOT NULL DEFAULT 'Student',     -- Student, Professor, Faculty, or Staff
    title TEXT NOT NULL DEFAULT '',           -- shown before the name, e.g. "Sophomore" or a clan name
    title_kind TEXT NOT NULL DEFAULT '',      -- where the title came from: "year", "role", or "clan:<id>"
    active_pet TEXT NOT NULL DEFAULT '',      -- key into pets.PETS
    pet_pity INTEGER NOT NULL DEFAULT 0,      -- summons since the last Legendary
    last_seen TEXT NOT NULL DEFAULT ''        -- for "online now" in Discover
);

CREATE TABLE IF NOT EXISTS user_pets (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pet_id TEXT NOT NULL,
    obtained_at TEXT NOT NULL,
    PRIMARY KEY (user_id, pet_id)
);

-- Chat. channel is "global", "clan:<clan id>", "class:<course>", or "dm:<lower user id>:<higher user id>".
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_channel ON messages (channel, id);

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
    ends_at TEXT NOT NULL,
    raid_id INTEGER REFERENCES raids(id)      -- set for raid parties (going to an event together)
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

-- OU athletics events from SoonerSports.com (see raids.py). id is SoonerSports' event id.
CREATE TABLE IF NOT EXISTS raids (
    id INTEGER PRIMARY KEY,
    sport TEXT NOT NULL,
    sport_slug TEXT NOT NULL DEFAULT '',
    opponent TEXT NOT NULL,
    at_vs TEXT NOT NULL,
    home_away TEXT NOT NULL,                  -- H, A, or N (neutral site)
    venue TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    starts_at TEXT NOT NULL,                  -- local time; 00:00 when only the day is known
    ends_at TEXT NOT NULL,                    -- end of the event's last day
    time_text TEXT NOT NULL DEFAULT '',       -- as SoonerSports shows it, e.g. "3:15 p.m. CT"
    tv TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    tickets_url TEXT NOT NULL DEFAULT '',
    synced_at TEXT NOT NULL,
    -- Raids students create themselves (ids start at CUSTOM_RAID_ID_START so they never collide with SoonerSports ids)
    creator_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    place_key TEXT NOT NULL DEFAULT '',       -- campus place for the map (a dungeon or venue key)
    boosted_until TEXT NOT NULL DEFAULT ''    -- pinned to the top of the Raids tab until this time
);

CREATE TABLE IF NOT EXISTS raid_checkins (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    raid_id INTEGER NOT NULL REFERENCES raids(id) ON DELETE CASCADE,
    checked_in_at TEXT NOT NULL,
    PRIMARY KEY (user_id, raid_id)
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
