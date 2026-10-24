"""Sooner Buddies: a campus RPG for OU students where studying together levels you up."""
import hashlib
import hmac
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps

import segno
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

import avatar
import campus
import db as db_module
import icons
import pets
import raids as raid_feed

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # don't send the login cookie on cross-site form posts
# Local development uses this SQLite file. Set DATABASE_URL (a Supabase Postgres connection string)
# to store everything in Supabase instead; see db.py.
DATABASE = os.path.join(app.root_path, "soonerbuddies.db")

# Only OU addresses can sign up. Set to "" to allow any email (handy for testing).
EMAIL_DOMAIN = "ou.edu"
YEARS = ["Freshman", "Sophomore", "Junior", "Senior", "Graduate"]
GENDERS = ["Prefer not to say", "Female", "Male", "Non-binary", "Other"]
ROLES = ["Student", "Professor", "Faculty", "Staff"]
ROLE_TITLES = {"Professor": "Prof.", "Faculty": "Faculty", "Staff": "Staff"}  # students wear their year instead
MAX_MESSAGE_LENGTH = 500
STARTING_CC = 150  # enough for a first item in the avatar shop

# Studying in a dungeon ("fighting") earns rewards per minute.
CC_PER_MINUTE = 1
XP_PER_MINUTE = 2
PARTY_BONUS = 1.5  # when studying with a party of 2+ members
MAX_SESSION_MINUTES = 240  # a forgotten session can't farm rewards forever

# Checking in at a raid (an OU athletics event) earns a flat reward, with the same party bonus.
RAID_CC = 50
RAID_XP = 100
RAID_SYNC_HOURS = 6  # how stale the SoonerSports.com data can get before the Raids page re-fetches it

# Raids students create. Boosting pins one to the top of the Raids tab.
RAID_CATEGORIES = ["Tailgate", "Watch party", "Club event", "Study jam", "Pickup game", "Other"]
CUSTOM_RAID_ID_START = 1_000_000_000  # SoonerSports ids are far below this, so the two never collide
BOOST_CC = 150
BOOST_HOURS = 24

ONLINE_MINUTES = 5  # "online" in Discover means seen within this many minutes
# Speeds up the study clock for live demos: DEMO_TIME_SCALE=60 counts each second as a minute.
TIME_SCALE = max(1, int(os.environ.get("DEMO_TIME_SCALE", "1")))

PARTY_HOURS = [1, 2, 3, 4]
CLAN_KINDS = ["Club", "Fraternity", "Sorority", "Academic", "Sports", "Other"]
CLAN_EMBLEMS = ["⚔️", "🛡️", "🐉", "🦅", "🔥", "⭐", "📚", "🎓", "⚙️", "🔬", "🎵", "🏈"]

# Study dungeons: real places to study around campus.
DUNGEONS = {
    "bizzell": {"name": "Bizzell Memorial Library", "kind": "Library",
                "blurb": "Quiet floors, group study rooms, and endless books."},
    "union": {"name": "Oklahoma Memorial Union", "kind": "Study lounge",
              "blurb": "Lounges and tables in the middle of campus, coffee nearby."},
    "gallogly": {"name": "Gallogly Hall", "kind": "Computer lab",
                 "blurb": "Computer labs for coding, projects, and late-night debugging."},
    "devon": {"name": "Devon Energy Hall", "kind": "Computer lab",
              "blurb": "Engineering labs and study tables."},
    "psc": {"name": "Physical Sciences Center", "kind": "Academic hall",
            "blurb": "Right next to your chemistry and physics classes."},
    "rawl": {"name": "Rawl Engineering Practice Facility", "kind": "Study space",
             "blurb": "Open space for engineering group work."},
    "price": {"name": "Price Hall", "kind": "Study lounge",
              "blurb": "Business school study spaces."},
    "sarkeys": {"name": "Sarkeys Energy Center", "kind": "Academic hall",
                "blurb": "A study stop between science and engineering classes."},
    "dale": {"name": "Dale Hall", "kind": "Academic hall",
             "blurb": "Classrooms and quiet corners between classes."},
    "dorms": {"name": "Residence hall lounge", "kind": "Study lounge",
              "blurb": "Study close to home in your hall's lounge."},
    "other": {"name": "Somewhere else on campus", "kind": "Wild area",
              "blurb": "Any other spot. Say where in the party details."},
}

# Leaderboard tabs: metric -> (column to rank by, label).
PLAYER_BOARDS = {
    "level": ("xp", "Highest level"),
    "cc": ("cc_earned", "Most Crimson Crystals"),
    "raids": ("raids", "Most raids"),
    "study": ("study_minutes", "Most time studying"),
}
CLAN_BOARDS = {
    "cc": ("cc", "Most Crimson Crystals"),
    "raids": ("raids", "Most raids"),
    "study": ("study", "Most time studying"),
}


def place(key):
    return DUNGEONS.get(key, DUNGEONS["other"])


# --- Database ---------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = db_module.connect(DATABASE)
    return g.db


def insert(db, sql, params):
    """Run an INSERT and return the new row's id (works on SQLite and Postgres)."""
    return db.execute(sql + " RETURNING id", params).fetchone()[0]


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Columns added after the first release. Older databases get them on startup.
ADDED_COLUMNS = {
    "parties": [("raid_id", "INTEGER REFERENCES raids(id)")],
    "users": [
        ("role", "TEXT NOT NULL DEFAULT 'Student'"),
        ("title", "TEXT NOT NULL DEFAULT ''"),
        ("title_kind", "TEXT NOT NULL DEFAULT ''"),
        ("active_pet", "TEXT NOT NULL DEFAULT ''"),
        ("pet_pity", "INTEGER NOT NULL DEFAULT 0"),
        ("last_seen", "TEXT NOT NULL DEFAULT ''"),
    ],
    "raids": [
        ("creator_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
        ("place_key", "TEXT NOT NULL DEFAULT ''"),
        ("boosted_until", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def init_db():
    db = get_db()
    if db_module.USING_POSTGRES:
        # Several web workers start at once; the lock makes them create tables one at a time.
        with app.open_resource("schema_postgres.sql") as f:  # already has every column
            db.executescript("SELECT pg_advisory_xact_lock(727274);\n" + f.read().decode())
        db.commit()
        return
    with app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode())
    for table, columns in ADDED_COLUMNS.items():
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns:
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    db.commit()


with app.app_context():
    init_db()


def stamp(dt):
    return dt.isoformat(sep=" ", timespec="seconds")


def now():
    return stamp(datetime.now())


def get_user(user_id):
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    return user


# --- Levels and rewards -----------------------------------------------------

LEVEL_TITLES = [(30, "Legend"), (20, "Champion"), (15, "Sage"), (10, "Scholar"), (5, "Apprentice"), (1, "Novice")]


def level_info(xp):
    """Going from level n to n+1 costs 100*n XP."""
    level, cost = 1, 100
    while xp >= cost:
        xp -= cost
        level += 1
        cost = 100 * level
    title = next(name for min_level, name in LEVEL_TITLES if level >= min_level)
    return {"level": level, "title": title, "progress": xp, "cost": cost, "percent": 100 * xp // cost}


def with_bonuses(cc, xp, party_bonus, pet_id):
    """Apply the party bonus and the active pet's boost to a base reward."""
    multiplier = PARTY_BONUS if party_bonus else 1
    cc_boost, xp_boost = pets.boosts(pet_id)
    return round(cc * multiplier * (1 + cc_boost / 100)), round(xp * multiplier * (1 + xp_boost / 100))


def fight_rewards(minutes, party_bonus, pet_id=None):
    """(CC, XP) earned for a dungeon run (study session)."""
    return with_bonuses(minutes * CC_PER_MINUTE, minutes * XP_PER_MINUTE, party_bonus, pet_id)


def raid_rewards(party_bonus, pet_id=None):
    """(CC, XP) earned for checking in at a raid."""
    return with_bonuses(RAID_CC, RAID_XP, party_bonus, pet_id)


def bonus_note(party_bonus, pet_id):
    """' (party bonus, Boomer +20% CC)' for reward messages, or ''."""
    notes = ["party bonus"] if party_bonus else []
    pet = pets.PETS.get(pet_id)
    if pet:
        notes.append(f"{pet['name']} +{pet['percent']}% {pet['boosts'].upper()}")
    return f" ({', '.join(notes)})" if notes else ""


def flash_level_up(old_xp, gained_xp):
    new_level = level_info(old_xp + gained_xp)["level"]
    if new_level > level_info(old_xp)["level"]:
        flash(f"Level up! You're now level {new_level}.", "level")


# --- Courses and matching ---------------------------------------------------

COURSE_RE = re.compile(r"([A-Z]+)\s*(\d+[A-Z]?)")


def normalize_course(raw):
    """'chem1315' or ' Chem  1315 ' -> 'CHEM 1315'. Anything else is just tidied up."""
    text = " ".join(raw.upper().split())
    m = COURSE_RE.fullmatch(text)
    return f"{m[1]} {m[2]}" if m else text


def parse_courses(raw):
    """'chem1315, math 1914' -> ['CHEM 1315', 'MATH 1914'] (deduplicated, order kept)."""
    courses = []
    for part in raw.split(","):
        course = normalize_course(part)
        if course and course not in courses:
            courses.append(course)
    return courses


def department(course):
    """'CHEM 1315' -> 'CHEM', so students in different chemistry classes still match."""
    m = COURSE_RE.fullmatch(course)
    return m[1] if m else course


def find_matches(me, limit=8):
    """Rank other students by shared classes, then shared departments, then major."""
    mine = set(parse_courses(me["courses"]))
    my_depts = {department(c) for c in mine}
    matches = []
    for other in get_db().execute("SELECT * FROM users WHERE id != ?", (me["id"],)):
        theirs = set(parse_courses(other["courses"]))
        shared = sorted(mine & theirs)
        shared_depts = sorted(my_depts & {department(c) for c in theirs})
        same_major = other["major"].strip().lower() == me["major"].strip().lower()
        score = 3 * len(shared) + len(shared_depts) + (2 if same_major else 0)
        if not score:
            continue
        if shared:
            reason = "Shares " + ", ".join(shared)
        elif shared_depts:
            reason = "Also takes " + ", ".join(shared_depts) + " classes"
        else:
            reason = f"Also majoring in {other['major']}"
        matches.append({"user": other, "reason": reason, "score": score})
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:limit]


# --- Parties ----------------------------------------------------------------

PARTY_SELECT = """
    SELECT p.*, u.name AS leader_name, COUNT(m.user_id) AS member_count,
           r.at_vs AS raid_at_vs, r.opponent AS raid_opponent
    FROM parties p
    JOIN users u ON u.id = p.leader_id
    LEFT JOIN party_members m ON m.party_id = p.id
    LEFT JOIN raids r ON r.id = p.raid_id
"""
PARTY_GROUP = "GROUP BY p.id, u.name, r.at_vs, r.opponent"  # Postgres wants every non-summed column listed


def party_info(row):
    """Party row -> dict with where it meets and whether it's meeting right now."""
    party = dict(row)
    if party["raid_id"]:
        party["place"] = {"name": f"{party['raid_at_vs']} {party['raid_opponent']}", "kind": "Raid", "blurb": ""}
    else:
        party["place"] = place(party["dungeon"])
    party["live"] = party["starts_at"] <= now() < party["ends_at"]
    return party


def open_parties(search=""):
    """Study parties that haven't ended, soonest first. `search` matches class, name, or dungeon."""
    rows = get_db().execute(
        PARTY_SELECT + " WHERE p.ends_at > ? AND p.raid_id IS NULL " + PARTY_GROUP + " ORDER BY p.starts_at", (now(),)
    ).fetchall()
    parties = [party_info(row) for row in rows]
    if search:
        text, course = search.lower(), normalize_course(search)
        parties = [p for p in parties
                   if course in p["course"] or text in p["name"].lower() or text in p["place"]["name"].lower()]
    return parties


def get_party(party_id):
    row = get_db().execute(PARTY_SELECT + " WHERE p.id = ? " + PARTY_GROUP, (party_id,)).fetchone()
    if row is None:
        abort(404)
    return party_info(row)


def attach_members(parties):
    """Give each open party its member rows, for the avatar stacks on party cards."""
    members = {}
    rows = get_db().execute(
        "SELECT m.party_id, u.* FROM party_members m"
        " JOIN users u ON u.id = m.user_id JOIN parties p ON p.id = m.party_id"
        " WHERE p.ends_at > ? ORDER BY m.joined_at",
        (now(),),
    )
    for row in rows:
        members.setdefault(row["party_id"], []).append(row)
    for party in parties:
        party["members"] = members.get(party["id"], [])
    return parties


def parties_for_user(user, parties):
    """Parties for the user's exact classes first, then ones in the same departments."""
    mine = set(parse_courses(user["courses"]))
    depts = {department(c) for c in mine}
    exact = [p for p in parties if p["course"] in mine]
    related = [p for p in parties if p["course"] not in mine and department(p["course"]) in depts]
    return exact + related


def my_party_ids():
    rows = get_db().execute(
        "SELECT m.party_id FROM party_members m JOIN parties p ON p.id = m.party_id"
        " WHERE m.user_id = ? AND p.ends_at > ?",
        (g.user["id"], now()),
    ).fetchall()
    return {row["party_id"] for row in rows}


def party_size(party_id):
    return get_db().execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (party_id,)).fetchone()[0]


# --- Study sessions ("fighting" in a dungeon) -------------------------------

def who_is_studying():
    """user id -> their running study session."""
    rows = get_db().execute("SELECT * FROM study_sessions WHERE ended_at IS NULL").fetchall()
    return {row["user_id"]: row for row in rows}


def dungeon_players():
    """Dungeon key -> users on a dungeon run there right now."""
    players = {}
    for row in get_db().execute(
        "SELECT s.dungeon AS spot, u.* FROM study_sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.ended_at IS NULL ORDER BY s.started_at"
    ):
        players.setdefault(row["spot"], []).append(row)
    return players


def raid_players():
    """Raid id -> users going (in one of its raid parties) or already checked in."""
    players = {}
    for row in get_db().execute(
        "SELECT x.raid_id AS raid, u.* FROM ("
        "   SELECT p.raid_id, m.user_id FROM parties p JOIN party_members m ON m.party_id = p.id"
        "   WHERE p.raid_id IS NOT NULL AND p.ends_at > ?"
        "   UNION SELECT raid_id, user_id FROM raid_checkins"
        " ) x JOIN users u ON u.id = x.user_id ORDER BY u.name",
        (now(),),
    ):
        players.setdefault(row["raid"], []).append(row)
    return players


# Every campus place a raid can be held at: dungeon rooms with a fixed spot, plus athletics venues.
CAMPUS_PLACES = {
    **{key: DUNGEONS[key]["name"] for key in campus.DUNGEON_SPOTS},
    **{key: venue["name"] for key, venue in campus.VENUES.items()},
}


def place_spot(key):
    """(lat, lng) of a dungeon room or venue, or None."""
    if key in campus.DUNGEON_SPOTS:
        return campus.DUNGEON_SPOTS[key]
    venue = campus.VENUES.get(key)
    return venue["spot"] if venue else None


def start_fight(dungeon, party_id=None):
    if g.fight:
        flash(f"You're already studying at {place(g.fight['dungeon'])['name']}. Finish that session first.", "error")
        return
    db = get_db()
    db.execute(
        "INSERT INTO study_sessions (user_id, dungeon, party_id, started_at) VALUES (?, ?, ?, ?)",
        (g.user["id"], dungeon, party_id, now()),
    )
    db.commit()
    flash(f"You entered {place(dungeon)['name']}. Your dungeon run has started; clear it when you're done studying.")


# --- Friends ----------------------------------------------------------------

def friend_relations():
    """Other user id -> 'friends', 'sent' (waiting on them), or 'received' (waiting on you)."""
    db, me = get_db(), g.user["id"]
    sent = {row[0] for row in db.execute("SELECT friend_id FROM friendships WHERE user_id = ?", (me,))}
    received = {row[0] for row in db.execute("SELECT user_id FROM friendships WHERE friend_id = ?", (me,))}
    relations = {uid: "sent" for uid in sent - received}
    relations.update({uid: "received" for uid in received - sent})
    relations.update({uid: "friends" for uid in sent & received})
    return relations


def friend_count(user_id):
    return get_db().execute(
        "SELECT COUNT(*) FROM friendships a JOIN friendships b"
        " ON b.user_id = a.friend_id AND b.friend_id = a.user_id WHERE a.user_id = ?",
        (user_id,),
    ).fetchone()[0]


# --- Clans ------------------------------------------------------------------

# A clan's stats are the sums of its members' stats.
CLAN_SELECT = """
    SELECT c.*, f.name AS founder_name, COUNT(m.user_id) AS members,
           CAST(COALESCE(SUM(u.xp), 0) AS INTEGER) AS xp,
           CAST(COALESCE(SUM(u.cc_earned), 0) AS INTEGER) AS cc,
           CAST(COALESCE(SUM(u.study_minutes), 0) AS INTEGER) AS study,
           CAST(COALESCE(SUM(u.raids), 0) AS INTEGER) AS raids
    FROM clans c
    LEFT JOIN users f ON f.id = c.founder_id
    LEFT JOIN clan_members m ON m.clan_id = c.id
    LEFT JOIN users u ON u.id = m.user_id
"""
CLAN_GROUP = "GROUP BY c.id, f.name"


def get_clan(clan_id):
    clan = get_db().execute(CLAN_SELECT + " WHERE c.id = ? " + CLAN_GROUP, (clan_id,)).fetchone()
    if clan is None:
        abort(404)
    return clan


def my_clan_ids():
    rows = get_db().execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (g.user["id"],)).fetchall()
    return {row["clan_id"] for row in rows}


# --- Titles -----------------------------------------------------------------

def title_options(user):
    """[(kind, text)] titles this user can wear: their year (or staff role) and each clan they're in."""
    if user["role"] in ROLE_TITLES:
        options = [("role", ROLE_TITLES[user["role"]])]
    else:
        options = [("year", user["year"])]
    clans = get_db().execute(
        "SELECT c.id, c.name FROM clan_members m JOIN clans c ON c.id = m.clan_id WHERE m.user_id = ? ORDER BY c.name",
        (user["id"],),
    )
    return options + [(f"clan:{clan['id']}", clan["name"]) for clan in clans]


def set_title(user_id, kind):
    """Wear the title of this kind, or no title if it isn't one of the user's options."""
    text = dict(title_options(get_user(user_id))).get(kind, "")
    get_db().execute("UPDATE users SET title = ?, title_kind = ? WHERE id = ?", (text, kind if text else "", user_id))


# --- Template helpers -------------------------------------------------------

app.add_template_filter(parse_courses, "courses")
app.add_template_global(avatar.render, "avatar_svg")
app.add_template_global(level_info)
app.add_template_global(place)


@app.template_filter("num")
def num(n):
    return f"{n:,}"


@app.template_filter("hours")
def hours(minutes):
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"


@app.template_filter("clock")
def clock(ts):
    return datetime.fromisoformat(ts).strftime("%I:%M %p").lstrip("0")


@app.template_filter("when")
def when(ts):
    dt = datetime.fromisoformat(ts)
    days = (dt.date() - datetime.now().date()).days
    day = {-1: "Yesterday", 0: "Today", 1: "Tomorrow"}.get(days, dt.strftime("%a %b %d"))
    return f"{day} {clock(ts)}"


@app.template_filter("day_label")
def day_label(day):
    """'2026-10-31' -> 'Today', 'Tomorrow', or 'Saturday, Oct 31'."""
    date = datetime.fromisoformat(day).date()
    days = (date - datetime.now().date()).days
    return {0: "Today", 1: "Tomorrow"}.get(days) or f"{date:%A}, {date:%b} {date.day}"


@app.template_global()
def display_name(user):
    """The user's name with their chosen title in front of it."""
    if not user["title"]:
        return user["name"]
    return Markup('<span class="title-tag">{}</span> {}').format(user["title"], user["name"])


@app.template_global()
def pet_of(user):
    return pets.PETS.get(user["active_pet"])


@app.template_global()
def is_online(user):
    return user["last_seen"] >= stamp(datetime.now() - timedelta(minutes=ONLINE_MINUTES))


@app.template_global()
def dungeon_icon(key, size=48):
    return icons.dungeon_icon(key, place(key)["name"], size)


@app.template_global()
def raid_icon(raid, size=32):
    return icons.raid_icon(raid["sport_slug"], raid["sport"], size)


@app.template_global()
def elapsed_seconds(ts):
    return max(0, int((datetime.now() - datetime.fromisoformat(ts)).total_seconds()))


@app.template_global()
def next_field():
    """Hidden input so a form post can send the user back to the page it came from."""
    return Markup(f'<input type="hidden" name="next" value="{escape(request.full_path)}">')


def back(default, **values):
    """Redirect to the form's `next` page if it's on this site, otherwise to `default`."""
    return redirect(safe_next(request.form.get("next")) or url_for(default, **values))


@app.context_processor
def constants():
    return {
        "years": YEARS, "genders": GENDERS, "roles": ROLES, "dungeons": DUNGEONS, "party_hours": PARTY_HOURS,
        "clan_kinds": CLAN_KINDS, "clan_emblems": CLAN_EMBLEMS, "slots": avatar.SLOTS,
        "skin_tones": avatar.SKIN_TONES, "starting_cc": STARTING_CC, "time_scale": TIME_SCALE,
        "rewards": {"cc": CC_PER_MINUTE, "xp": XP_PER_MINUTE, "bonus": round((PARTY_BONUS - 1) * 100),
                    "max_hours": MAX_SESSION_MINUTES // 60},
    }


# --- Auth -------------------------------------------------------------------

@app.before_request
def load_user():
    g.user = g.fight = None
    g.friend_requests = 0
    user_id = session.get("user_id")
    if user_id is None or request.endpoint == "static":
        return
    db = get_db()
    g.user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if g.user is None:
        return
    g.fight = db.execute(
        "SELECT * FROM study_sessions WHERE user_id = ? AND ended_at IS NULL", (user_id,)
    ).fetchone()
    g.friend_requests = db.execute(
        "SELECT COUNT(*) FROM friendships a WHERE a.friend_id = ? AND NOT EXISTS"
        " (SELECT 1 FROM friendships b WHERE b.user_id = a.friend_id AND b.friend_id = a.user_id)",
        (user_id,),
    ).fetchone()[0]
    # Note activity for "online now", at most once a minute.
    if g.user["last_seen"] < stamp(datetime.now() - timedelta(minutes=1)):
        db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (now(), user_id))
        db.commit()


def safe_next(target):
    """`target` if it's a path on this site (not an open redirect), else None."""
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            # Come back here after logging in, e.g. after scanning a dungeon's QR code.
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def profile_error(form):
    if not (form.get("name", "").strip() and form.get("major", "").strip()):
        return "Please fill in your name and major."
    if form.get("gender") not in GENDERS or form.get("year") not in YEARS or form.get("role", "Student") not in ROLES:
        return "Please pick your role, gender, and year."
    if not parse_courses(form.get("courses", "")):
        return "Add at least one class so we can match you."
    return None


def signup_error(form):
    email = form.get("email", "").strip().lower()
    if EMAIL_DOMAIN and not email.endswith("@" + EMAIL_DOMAIN):
        return f"Please sign up with your @{EMAIL_DOMAIN} email."
    if len(form.get("password", "")) < 6:
        return "Password must be at least 6 characters."
    return profile_error(form)


def profile_values(form):
    """(name, gender, major, year, courses, role) from a validated profile form."""
    return (form["name"].strip()[:40], form["gender"], form["major"].strip()[:60], form["year"],
            ", ".join(parse_courses(form["courses"])), form.get("role", "Student"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = request.form
    if request.method == "POST":
        error = signup_error(form)
        if not error:
            db = get_db()
            try:
                new_id = insert(db,
                    "INSERT INTO users (email, password_hash, cc, name, gender, major, year, courses, role)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (form["email"].strip().lower(), generate_password_hash(form["password"]), STARTING_CC,
                     *profile_values(form)),
                )
                set_title(new_id, "role" if form.get("role", "Student") in ROLE_TITLES else "year")
                db.commit()
            except db_module.IntegrityError:
                db.rollback()
                error = "An account with that email already exists."
            else:
                session.clear()
                session["user_id"] = new_id
                flash(f"Welcome, adventurer! Here's {STARTING_CC} Crimson Crystals to style your avatar.")
                return redirect(url_for("dashboard"))
        flash(error, "error")
    return render_template("signup.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    form = request.form
    if request.method == "POST":
        email = form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(safe_next(request.args.get("next")) or url_for("dashboard"))
        flash("Wrong email or password.", "error")
    return render_template("login.html", form=form)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# --- Home, dashboard, and profiles ------------------------------------------

@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("index.html", studying=len(who_is_studying()), parties=attach_members(open_parties()))


@app.route("/dashboard")
@login_required
def dashboard():
    parties = attach_members(open_parties())
    mine = my_party_ids()
    relations = friend_relations()
    return render_template(
        "dashboard.html",
        my_parties=[p for p in parties if p["id"] in mine],
        suggested=[p for p in parties_for_user(g.user, parties) if p["id"] not in mine][:4],
        matches=find_matches(g.user, limit=5),
        relations=relations,
        friend_count=sum(1 for status in relations.values() if status == "friends"),
        studying=who_is_studying(),
    )


@app.route("/players/<int:user_id>")
@login_required
def player(user_id):
    user = get_user(user_id)
    db = get_db()
    clans = db.execute(
        "SELECT c.* FROM clan_members m JOIN clans c ON c.id = m.clan_id WHERE m.user_id = ? ORDER BY c.name",
        (user_id,),
    ).fetchall()
    runs = db.execute(
        "SELECT * FROM study_sessions WHERE user_id = ? AND ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 5",
        (user_id,),
    ).fetchall()
    return render_template(
        "player.html",
        player=user,
        clans=clans,
        runs=runs,
        friend_count=friend_count(user_id),
        relation=friend_relations().get(user_id),
        studying=who_is_studying().get(user_id),
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        error = profile_error(request.form)
        if not error:
            db = get_db()
            db.execute(
                "UPDATE users SET name = ?, gender = ?, major = ?, year = ?, courses = ?, role = ? WHERE id = ?",
                (*profile_values(request.form), g.user["id"]),
            )
            # Re-resolve the title too, so a year or role change shows up in it.
            set_title(g.user["id"], request.form.get("title", g.user["title_kind"]))
            db.commit()
            flash("Profile saved.")
            return redirect(url_for("player", user_id=g.user["id"]))
        flash(error, "error")
        return render_template("profile.html", form=request.form, titles=title_options(g.user))
    return render_template("profile.html", form=dict(g.user), titles=title_options(g.user))


# --- Avatar and crystal shop ------------------------------------------------

def owned_items():
    rows = get_db().execute("SELECT item_id FROM inventory WHERE user_id = ?", (g.user["id"],)).fetchall()
    return {row["item_id"] for row in rows} | avatar.FREE_ITEMS


def save_outfit(outfit):
    get_db().execute("UPDATE users SET outfit = ? WHERE id = ?", (json.dumps(outfit), g.user["id"]))


@app.route("/avatar")
@login_required
def avatar_page():
    slot = request.args.get("slot")
    if slot not in avatar.SLOTS:
        slot = None
    items = {item_id: item for item_id, item in avatar.ITEMS.items() if slot in (None, item["slot"])}
    return render_template(
        "avatar.html",
        items=items,
        slot=slot,
        owned=owned_items(),
        outfit=avatar.outfit_of(g.user),
        catalog=avatar.ITEMS,
        required=avatar.REQUIRED_SLOTS,
    )


@app.post("/avatar/buy/<item_id>")
@login_required
def buy_item(item_id):
    item = avatar.ITEMS.get(item_id)
    if item is None:
        abort(404)
    if item_id in owned_items():
        flash(f"You already own {item['name']}.")
    elif g.user["cc"] < item["price"]:
        flash(f"You need {item['price'] - g.user['cc']} more CC for {item['name']}. Go clear a dungeon!", "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET cc = cc - ? WHERE id = ?", (item["price"], g.user["id"]))
        db.execute("INSERT INTO inventory (user_id, item_id) VALUES (?, ?)", (g.user["id"], item_id))
        save_outfit({**avatar.outfit_of(g.user), item["slot"]: item_id})
        db.commit()
        flash(f"You bought and equipped {item['name']}!")
    return back("avatar_page")


@app.post("/avatar/equip/<item_id>")
@login_required
def equip_item(item_id):
    item = avatar.ITEMS.get(item_id)
    if item is None:
        abort(404)
    if item_id not in owned_items():
        flash("Buy that item first.", "error")
    else:
        save_outfit({**avatar.outfit_of(g.user), item["slot"]: item_id})
        get_db().commit()
    return back("avatar_page")


@app.post("/avatar/unequip/<slot>")
@login_required
def unequip(slot):
    if slot in avatar.SLOTS and slot not in avatar.REQUIRED_SLOTS:
        outfit = avatar.outfit_of(g.user)
        outfit.pop(slot, None)
        save_outfit(outfit)
        get_db().commit()
    return back("avatar_page")


@app.post("/avatar/skin")
@login_required
def set_skin():
    skin = request.form.get("skin")
    if skin in avatar.SKIN_TONES:
        db = get_db()
        db.execute("UPDATE users SET skin = ? WHERE id = ?", (skin, g.user["id"]))
        db.commit()
    return back("avatar_page")


# --- Parties ----------------------------------------------------------------

@app.route("/pets")
@login_required
def pet_page():
    owned = {row["pet_id"] for row in get_db().execute("SELECT pet_id FROM user_pets WHERE user_id = ?", (g.user["id"],))}
    return render_template(
        "pets.html",
        pets=pets.PETS,
        rarities=pets.RARITIES,
        owned=owned,
        last=session.pop("last_summon", None),
        cost=pets.SUMMON_COST,
        refund=pets.DUPLICATE_REFUND,
        pity_left=pets.PITY - g.user["pet_pity"],
    )


@app.post("/pets/summon")
@login_required
def summon_pet():
    if g.user["cc"] < pets.SUMMON_COST:
        flash(f"A summon costs {pets.SUMMON_COST} CC. Clear a dungeon or join a raid to earn more.", "error")
        return redirect(url_for("pet_page"))
    pet_id, pity = pets.summon(g.user["pet_pity"])
    db = get_db()
    is_new = db.execute(
        "INSERT INTO user_pets (user_id, pet_id, obtained_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING", (g.user["id"], pet_id, now())
    ).rowcount == 1
    refund = 0 if is_new else pets.DUPLICATE_REFUND
    db.execute(
        "UPDATE users SET cc = cc - ? + ?, pet_pity = ?,"
        " active_pet = CASE WHEN active_pet = '' THEN ? ELSE active_pet END WHERE id = ?",
        (pets.SUMMON_COST, refund, pity, pet_id, g.user["id"]),
    )
    db.commit()
    session["last_summon"] = {"pet": pet_id, "new": is_new}
    return redirect(url_for("pet_page"))


@app.post("/pets/<pet_id>/activate")
@login_required
def activate_pet(pet_id):
    owns = get_db().execute(
        "SELECT 1 FROM user_pets WHERE user_id = ? AND pet_id = ?", (g.user["id"], pet_id)
    ).fetchone()
    if not owns:
        abort(404)
    db = get_db()
    db.execute("UPDATE users SET active_pet = ? WHERE id = ?", (pet_id, g.user["id"]))
    db.commit()
    flash(f"{pets.PETS[pet_id]['name']} is now your active pet.")
    return back("pet_page")


@app.route("/parties")
@login_required
def party_list():
    q = request.args.get("q", "").strip()
    parties = attach_members(open_parties(q))
    mine = my_party_ids()
    if q:
        sections = [("Search results", parties)]
    else:
        yours = [p for p in parties if p["id"] in mine]
        for_you = [p for p in parties_for_user(g.user, parties) if p["id"] not in mine]
        shown = {p["id"] for p in yours + for_you}
        sections = [("Your parties", yours), ("For your classes", for_you),
                    ("More open parties", [p for p in parties if p["id"] not in shown])]
    return render_template("parties.html", sections=sections, q=q, mine=mine)


@app.route("/parties/new", methods=["GET", "POST"])
@login_required
def party_new():
    form = request.form
    if request.method == "POST":
        name = form.get("name", "").strip()[:60]
        course = normalize_course(form.get("course", ""))[:20]
        dungeon = form.get("dungeon", "")
        hours_open = form.get("hours", type=int)
        capacity = form.get("capacity", type=int)
        try:
            start = datetime.fromisoformat(form["starts_at"]) if form.get("starts_at") else datetime.now()
        except ValueError:
            start = None

        error = None
        if not (name and course):
            error = "Give your party a name and a class."
        elif dungeon not in DUNGEONS:
            error = "Pick a dungeon to meet in."
        elif start is None or not (datetime.now() - timedelta(minutes=10) <= start <= datetime.now() + timedelta(days=14)):
            error = "Pick a start time within the next two weeks."
        elif hours_open not in PARTY_HOURS or not 2 <= (capacity or 0) <= 12:
            error = "Pick a length and a party size from 2 to 12."
        if error:
            flash(error, "error")
        else:
            start = max(start, datetime.now())
            db = get_db()
            new_id = insert(db,
                "INSERT INTO parties (leader_id, name, course, dungeon, spot, description, capacity, starts_at, ends_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], name, course, dungeon, form.get("spot", "").strip()[:60],
                 form.get("description", "").strip()[:200], capacity,
                 stamp(start), stamp(start + timedelta(hours=hours_open))),
            )
            db.execute(
                "INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
                (new_id, g.user["id"], now()),
            )
            db.commit()
            flash("Your party is up! Classmates taking that class will see it first.")
            return redirect(url_for("party_detail", party_id=new_id))
    return render_template("party_new.html", form=form)


@app.route("/parties/<int:party_id>")
@login_required
def party_detail(party_id):
    party = get_party(party_id)
    members = get_db().execute(
        "SELECT u.* FROM party_members m JOIN users u ON u.id = m.user_id WHERE m.party_id = ? ORDER BY m.joined_at",
        (party_id,),
    ).fetchall()
    raid = get_raid(party["raid_id"]) if party["raid_id"] else None
    return render_template(
        "party_detail.html",
        party=party,
        raid=raid,
        checked_in=raid is not None and checked_in(raid["id"]),
        members=members,
        is_member=any(m["id"] == g.user["id"] for m in members),
        is_leader=party["leader_id"] == g.user["id"],
        fighting={uid for uid, s in who_is_studying().items() if s["party_id"] == party_id},
        ended=party["ends_at"] <= now(),
    )


@app.post("/parties/<int:party_id>/join")
@login_required
def join_party(party_id):
    party = get_party(party_id)
    if party["ends_at"] <= now():
        flash("That party has already ended.", "error")
    elif party["member_count"] >= party["capacity"]:
        flash("Sorry, that party is full.", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (party_id, g.user["id"], now()),
        )
        db.commit()
        if party["raid_id"]:
            where = party["spot"]
        else:
            where = party["place"]["name"] + (f", {party['spot']}" if party["spot"] else "")
        flash(f"You joined {party['name']}! Meet at {where}.")
    return redirect(url_for("party_detail", party_id=party_id))


@app.post("/parties/<int:party_id>/leave")
@login_required
def leave_party(party_id):
    party = get_party(party_id)
    if party["leader_id"] == g.user["id"]:
        flash("You lead this party, so disband it instead.", "error")
        return redirect(url_for("party_detail", party_id=party_id))
    db = get_db()
    db.execute("DELETE FROM party_members WHERE party_id = ? AND user_id = ?", (party_id, g.user["id"]))
    db.commit()
    flash(f"You left {party['name']}.")
    return redirect(url_for("raid_detail", raid_id=party["raid_id"]) if party["raid_id"] else url_for("party_list"))


@app.post("/parties/<int:party_id>/disband")
@login_required
def disband_party(party_id):
    party = get_party(party_id)
    if party["leader_id"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("UPDATE parties SET ends_at = ? WHERE id = ?", (now(), party_id))
    db.commit()
    flash(f"{party['name']} has been disbanded.")
    return redirect(url_for("raid_detail", raid_id=party["raid_id"]) if party["raid_id"] else url_for("party_list"))


@app.post("/parties/<int:party_id>/study")
@login_required
def party_study(party_id):
    party = get_party(party_id)
    is_member = get_db().execute(
        "SELECT 1 FROM party_members WHERE party_id = ? AND user_id = ?", (party_id, g.user["id"])
    ).fetchone()
    if party["raid_id"]:
        flash("Raid parties check in at the event instead of starting a study session.", "error")
    elif not is_member:
        flash("Join the party first.", "error")
    elif not party["live"]:
        flash("This party isn't meeting right now.", "error")
    else:
        start_fight(party["dungeon"], party_id)
    return redirect(url_for("party_detail", party_id=party_id))


# --- Dungeons and raids -----------------------------------------------------

@app.route("/dungeons")
@login_required
def dungeon_list():
    live = Counter(p["dungeon"] for p in open_parties() if p["live"])
    return render_template("dungeons.html", players=dungeon_players(), live=live)


@app.post("/dungeons/<key>/enter")
@login_required
def enter_dungeon(key):
    if key not in DUNGEONS:
        abort(404)
    start_fight(key)
    return back("dungeon_list")


@app.post("/fight/start")
@login_required
def start_session():
    """The dashboard's "Start the clock" form: same as entering a dungeon, picked from a dropdown."""
    dungeon = request.form.get("dungeon")
    if dungeon not in DUNGEONS:
        abort(400)
    start_fight(dungeon)
    return redirect(url_for("dashboard"))


@app.post("/fight/finish")
@login_required
def finish_fight():
    fight = g.fight
    if fight is None:
        return back("dashboard")
    minutes = min(MAX_SESSION_MINUTES, elapsed_seconds(fight["started_at"]) * TIME_SCALE // 60)
    bonus = fight["party_id"] is not None and party_size(fight["party_id"]) >= 2
    cc, xp = fight_rewards(minutes, bonus, g.user["active_pet"])
    db = get_db()
    db.execute(
        "UPDATE study_sessions SET ended_at = ?, minutes = ?, cc = ?, xp = ? WHERE id = ?",
        (now(), minutes, cc, xp, fight["id"]),
    )
    db.execute(
        "UPDATE users SET cc = cc + ?, cc_earned = cc_earned + ?, xp = xp + ?, study_minutes = study_minutes + ?"
        " WHERE id = ?",
        (cc, cc, xp, minutes, g.user["id"]),
    )
    db.commit()
    if minutes == 0:
        flash("Session ended. Study for at least a minute to earn rewards.")
    else:
        flash(f"Dungeon cleared: {minutes} min studied. Loot: +{cc} CC, +{xp} XP{bonus_note(bonus, g.user['active_pet'])}.")
        flash_level_up(g.user["xp"], xp)
    return back("dashboard")


def raid_info(row):
    """Raid row -> dict with display fields the templates need."""
    raid = dict(row)
    today = datetime.now().date().isoformat()
    raid["custom"] = raid["creator_id"] is not None  # made by a student rather than from SoonerSports.com
    raid["title"] = raid["opponent"] if raid["custom"] else f"{raid['sport']} {raid['at_vs']} {raid['opponent']}"
    raid["where"] = ", ".join(part for part in (raid["venue"], raid["city"]) if part) or "Location TBA"
    raid["description"] = raid["note"] if raid["custom"] else raid_feed.describe(raid)
    raid["day"] = max(raid["starts_at"][:10], today)  # multi-day events still running show under today
    raid["is_today"] = raid["starts_at"][:10] <= today <= raid["ends_at"][:10]
    raid["boosted"] = raid["boosted_until"] > now()
    raid["spot_key"] = raid["place_key"] or campus.venue_for(raid["venue"])  # for the map; None if off campus
    slug = raid["sport_slug"]
    raid["schedule_url"] = (None if raid["custom"] else
                            f"https://soonersports.com/sports/{slug}/schedule" if slug else "https://soonersports.com/calendar")
    return raid


def get_raid(raid_id):
    row = get_db().execute("SELECT * FROM raids WHERE id = ?", (raid_id,)).fetchone()
    if row is None:
        abort(404)
    return raid_info(row)


def refresh_raids():
    """Re-fetch events from SoonerSports.com when what we have is more than a few hours old."""
    db = get_db()
    last_sync = db.execute("SELECT MAX(synced_at) FROM raids").fetchone()[0]
    if last_sync and last_sync > stamp(datetime.now() - timedelta(hours=RAID_SYNC_HOURS)):
        return
    try:
        raid_feed.sync(db)
    except (OSError, ValueError, KeyError) as exc:  # offline, feed changed, etc.: keep showing what we have
        app.logger.warning("Couldn't sync raids from SoonerSports.com: %s", exc)


def raid_party_for(raid_id):
    """The current user's party for this raid, if they're in one."""
    return get_db().execute(
        "SELECT p.id FROM parties p JOIN party_members m ON m.party_id = p.id WHERE p.raid_id = ? AND m.user_id = ?",
        (raid_id, g.user["id"]),
    ).fetchone()


def checked_in(raid_id):
    return get_db().execute(
        "SELECT 1 FROM raid_checkins WHERE raid_id = ? AND user_id = ?", (raid_id, g.user["id"])
    ).fetchone() is not None


@app.route("/raids")
@login_required
def raid_list():
    refresh_raids()
    db = get_db()
    where = request.args.get("where", "all")
    sport = request.args.get("sport", "")
    sql = ("SELECT r.*, (SELECT COUNT(*) FROM parties p WHERE p.raid_id = r.id AND p.ends_at > ?) AS party_count"
           " FROM raids r WHERE r.ends_at > ?")
    args = [now(), now()]
    if where == "home":
        sql += " AND r.home_away = 'H'"
    elif where == "away":
        sql += " AND r.home_away != 'H'"
    if sport:
        sql += " AND r.sport = ?"
        args.append(sport)
    raids = sorted((raid_info(row) for row in db.execute(sql, args)), key=lambda r: (r["day"], r["starts_at"]))
    sports = [row[0] for row in db.execute("SELECT DISTINCT sport FROM raids WHERE ends_at > ? ORDER BY sport", (now(),))]
    my_raids = {row[0] for row in db.execute(
        "SELECT DISTINCT p.raid_id FROM parties p JOIN party_members m ON m.party_id = p.id"
        " WHERE m.user_id = ? AND p.raid_id IS NOT NULL", (g.user["id"],))}
    return render_template(
        "raids.html",
        boosted=[r for r in raids if r["boosted"]],
        raids=[r for r in raids if not r["boosted"]],
        players=raid_players(),
        sports=sports, where=where, sport=sport, my_raids=my_raids,
    )


@app.route("/raids/new", methods=["GET", "POST"])
@login_required
def raid_new():
    """Students can create their own raids: tailgates, watch parties, club events..."""
    form = request.form
    if request.method == "POST":
        name = form.get("name", "").strip()[:60]
        category, place_key = form.get("category"), form.get("place")
        hours_long = form.get("hours", type=int)
        try:
            start = datetime.fromisoformat(form.get("starts_at", ""))
        except ValueError:
            start = None
        error = None
        if not name:
            error = "Give your raid a name."
        elif category not in RAID_CATEGORIES or place_key not in CAMPUS_PLACES:
            error = "Pick a type of raid and a place on campus."
        elif start is None or not (datetime.now() - timedelta(minutes=10) <= start <= datetime.now() + timedelta(days=30)):
            error = "Pick a start time within the next 30 days."
        elif hours_long not in range(1, 7):
            error = "Raids can last 1 to 6 hours."
        if error:
            flash(error, "error")
        else:
            start = max(start, datetime.now()).replace(second=0, microsecond=0)
            end = start + timedelta(hours=hours_long)
            db = get_db()
            raid_id = max(CUSTOM_RAID_ID_START, (db.execute("SELECT MAX(id) FROM raids").fetchone()[0] or 0) + 1)
            db.execute(
                "INSERT INTO raids (id, sport, sport_slug, opponent, at_vs, home_away, venue, city, starts_at, ends_at,"
                " time_text, tv, note, tickets_url, synced_at, creator_id, place_key)"
                " VALUES (?, ?, 'custom', ?, '', 'H', ?, 'Norman, Okla.', ?, ?, ?, '', ?, '', ?, ?, ?)",
                (raid_id, category, name, CAMPUS_PLACES[place_key], stamp(start), stamp(end), clock(stamp(start)),
                 form.get("description", "").strip()[:300], now(), g.user["id"], place_key),
            )
            # The host's own raid party, so people can join right away.
            new_id = insert(db,
                "INSERT INTO parties (leader_id, name, course, dungeon, spot, description, capacity, starts_at, ends_at, raid_id)"
                " VALUES (?, ?, ?, 'other', ?, '', 20, ?, ?, ?)",
                (g.user["id"], f"{g.user['name'].split()[0]}'s crew", category, CAMPUS_PLACES[place_key],
                 stamp(start), stamp(end), raid_id),
            )
            db.execute("INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
                       (new_id, g.user["id"], now()))
            db.commit()
            flash(f"Raid created. Boost it for {BOOST_CC} CC to pin it to the top of the Raids tab.")
            return redirect(url_for("raid_detail", raid_id=raid_id))
    return render_template("raid_new.html", form=form, categories=RAID_CATEGORIES, places=CAMPUS_PLACES)


@app.post("/raids/<int:raid_id>/boost")
@login_required
def raid_boost(raid_id):
    """The raid's creator spends CC to pin it to the top of the Raids tab for a day (stacks)."""
    raid = get_raid(raid_id)
    if raid["creator_id"] != g.user["id"]:
        abort(403)
    ends = datetime.fromisoformat(raid["ends_at"])
    current = datetime.fromisoformat(raid["boosted_until"]) if raid["boosted"] else datetime.now()
    if ends <= datetime.now():
        flash("That raid is over.", "error")
    elif current >= ends:
        flash("Your raid is already boosted until it ends.")
    elif g.user["cc"] < BOOST_CC:
        flash(f"Boosting costs {BOOST_CC} CC. Clear a dungeon to earn more.", "error")
    else:
        until = min(current + timedelta(hours=BOOST_HOURS), ends)
        db = get_db()
        db.execute("UPDATE raids SET boosted_until = ? WHERE id = ?", (stamp(until), raid_id))
        db.execute("UPDATE users SET cc = cc - ? WHERE id = ?", (BOOST_CC, g.user["id"]))
        db.commit()
        flash(f"Boosted! {raid['title']} is pinned to the top of the Raids tab until {when(stamp(until))}.")
    return redirect(url_for("raid_detail", raid_id=raid_id))


@app.route("/raids/<int:raid_id>")
@login_required
def raid_detail(raid_id):
    raid = get_raid(raid_id)
    rows = get_db().execute(
        PARTY_SELECT + " WHERE p.raid_id = ? AND p.ends_at > ? " + PARTY_GROUP + " ORDER BY p.starts_at", (raid_id, now())
    ).fetchall()
    # Suggest meeting an hour before the start, when the start time is known.
    start = datetime.fromisoformat(raid["starts_at"])
    suggested_meet = ""
    if start.time() != datetime.min.time() and start - timedelta(hours=1) > datetime.now():
        suggested_meet = (start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    return render_template(
        "raid_detail.html",
        raid=raid,
        creator=get_user(raid["creator_id"]) if raid["custom"] else None,
        parties=attach_members([party_info(row) for row in rows]),
        players=raid_players().get(raid_id, []),
        my_party=raid_party_for(raid_id),
        checked_in=checked_in(raid_id),
        suggested_meet=suggested_meet,
        raid_reward=(RAID_CC, RAID_XP),
        boost_cc=BOOST_CC,
        boost_hours=BOOST_HOURS,
        now_stamp=now(),
    )


@app.post("/raids/<int:raid_id>/parties")
@login_required
def raid_party_new(raid_id):
    raid = get_raid(raid_id)
    form = request.form
    name = form.get("name", "").strip()[:60]
    spot = form.get("spot", "").strip()[:60]
    capacity = form.get("capacity", type=int)
    try:
        meet = datetime.fromisoformat(form["meet_at"]) if form.get("meet_at") else datetime.now()
    except ValueError:
        meet = None
    ends = datetime.fromisoformat(raid["ends_at"])
    if not (name and spot):
        flash("Give your raid party a name and a place to meet.", "error")
    elif meet is None or not (datetime.now() - timedelta(minutes=10) <= meet < ends):
        flash("Pick a meeting time between now and the end of the event.", "error")
    elif not 2 <= (capacity or 0) <= 20:
        flash("Pick a party size from 2 to 20.", "error")
    else:
        db = get_db()
        new_id = insert(db,
            "INSERT INTO parties (leader_id, name, course, dungeon, spot, description, capacity, starts_at, ends_at, raid_id)"
            " VALUES (?, ?, ?, 'other', ?, ?, ?, ?, ?, ?)",
            (g.user["id"], name, raid["sport"], spot, form.get("description", "").strip()[:200], capacity,
             stamp(max(meet, datetime.now())), raid["ends_at"], raid_id),
        )
        db.execute(
            "INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
            (new_id, g.user["id"], now()),
        )
        db.commit()
        flash(f"Raid party posted for {raid['title']}.")
        return redirect(url_for("party_detail", party_id=new_id))
    return redirect(url_for("raid_detail", raid_id=raid_id))


@app.post("/raids/<int:raid_id>/checkin")
@login_required
def raid_checkin(raid_id):
    check_in(get_raid(raid_id))
    return back("raid_detail", raid_id=raid_id)


def check_in(raid, via_qr=False):
    """Check the current user in at a raid. Scanning the raid's QR code works without a party
    (being there is the proof); the button is for raid party members."""
    raid_id = raid["id"]
    party = raid_party_for(raid_id)
    if not raid["is_today"]:
        flash("Check-in opens on the day of the event.", "error")
    elif party is None and not via_qr:
        flash("Join or start a raid party for this event first, or scan the raid's QR code there.", "error")
    elif checked_in(raid_id):
        flash("You already checked in at this raid.")
    else:
        bonus = party is not None and party_size(party["id"]) >= 2
        cc, xp = raid_rewards(bonus, g.user["active_pet"])
        db = get_db()
        db.execute(
            "INSERT INTO raid_checkins (user_id, raid_id, checked_in_at) VALUES (?, ?, ?)", (g.user["id"], raid_id, now())
        )
        db.execute(
            "UPDATE users SET cc = cc + ?, cc_earned = cc_earned + ?, xp = xp + ?, raids = raids + 1 WHERE id = ?",
            (cc, cc, xp, g.user["id"]),
        )
        db.commit()
        flash(f"Raid joined: {raid['title']}. Loot: +{cc} CC, +{xp} XP{bonus_note(bonus, g.user['active_pet'])}.")
        flash_level_up(g.user["xp"], xp)


# --- QR codes ---------------------------------------------------------------
# Each dungeon room and raid has a QR code to post at the spot. Scanning it starts a dungeon run
# or checks you in at the raid. The token stops people from typing in made-up scan links.

def qr_token(kind, ident):
    message = f"{kind}:{ident}".encode()
    return hmac.new(app.config["SECRET_KEY"].encode(), message, hashlib.sha256).hexdigest()[:16]


@app.template_global()
def qr_svg(kind, ident, scale=4):
    url = url_for("scan_code", kind=kind, ident=ident, t=qr_token(kind, ident), _external=True)
    return Markup(segno.make(url, error="m").svg_inline(scale=scale, dark="#2a1c18", light="#fffdf6"))


@app.route("/qr/<kind>/<ident>")
@login_required
def qr_page(kind, ident):
    """A printable QR code to post at a dungeon room or raid."""
    if kind == "dungeon" and ident in campus.DUNGEON_SPOTS:
        title, action = place(ident)["name"], "start a dungeon run here"
    elif kind == "raid" and ident.isdigit():
        title, action = get_raid(int(ident))["title"], "check in at this raid"
    else:
        abort(404)
    return render_template("qr.html", kind=kind, ident=ident, title=title, action=action)


@app.route("/scan")
@login_required
def scanner():
    return render_template("scan.html")


@app.route("/scan/<kind>/<ident>")
@login_required
def scan_code(kind, ident):
    """Where a scanned QR code lands."""
    if not hmac.compare_digest(request.args.get("t", ""), qr_token(kind, ident)):
        flash("That QR code isn't a valid Sooner Buddies code.", "error")
        return redirect(url_for("scanner"))
    if kind == "dungeon" and ident in DUNGEONS:
        if g.fight and g.fight["dungeon"] == ident:
            flash(f"You're already on a dungeon run in {place(ident)['name']}.")
        else:
            start_fight(ident)
        return redirect(url_for("dungeon_list"))
    if kind == "raid" and ident.isdigit():
        raid = get_raid(int(ident))
        check_in(raid, via_qr=True)
        return redirect(url_for("raid_detail", raid_id=raid["id"]))
    abort(404)


# --- Campus map -------------------------------------------------------------

@app.route("/map")
@login_required
def campus_map():
    in_dungeon = dungeon_players()
    markers = []
    for key, (lat, lng) in campus.DUNGEON_SPOTS.items():
        people = in_dungeon.get(key, [])
        markers.append({
            "kind": "dungeon", "lat": lat, "lng": lng, "count": len(people), "name": place(key)["name"],
            "icon": str(dungeon_icon(key, 40)),
            "popup": render_template("_spot_popup.html", kind="dungeon", key=key, title=place(key)["name"],
                                     subtitle=place(key)["kind"], people=people),
        })
    # Raids in the next week at a campus place, one marker per place.
    going = raid_players()
    week = get_db().execute(
        "SELECT * FROM raids WHERE ends_at > ? AND starts_at < ? ORDER BY starts_at",
        (now(), stamp(datetime.now() + timedelta(days=7))),
    )
    by_place = {}
    for raid in map(raid_info, week):
        if raid["spot_key"] and place_spot(raid["spot_key"]):
            by_place.setdefault(raid["spot_key"], []).append(raid)
    for key, raids_here in by_place.items():
        lat, lng = place_spot(key)
        if key in campus.DUNGEON_SPOTS:
            lat += 0.00028  # sit just above the dungeon room's own marker
        raids_here.sort(key=lambda r: (not r["boosted"], r["starts_at"]))
        markers.append({
            "kind": "raid", "lat": lat, "lng": lng, "name": CAMPUS_PLACES[key],
            "count": sum(len(going.get(r["id"], [])) for r in raids_here),
            "icon": str(raid_icon(raids_here[0], 24)),
            "popup": render_template("_raid_popup.html", place_name=CAMPUS_PLACES[key], raids=raids_here, going=going),
        })
    return render_template("map.html", markers=markers, outline=campus.OUTLINE, center=campus.CENTER)


# --- Discover ---------------------------------------------------------------

GENERIC_MAJOR_WORDS = {"and", "of", "the", "in", "science", "sciences", "studies", "arts", "&"}


def major_words(major):
    return {word for word in major.lower().split() if word not in GENERIC_MAJOR_WORDS}


@app.route("/discover")
@login_required
def discover():
    tab = request.args.get("tab", "online")
    me = g.user
    others = get_db().execute("SELECT * FROM users WHERE id != ? ORDER BY name", (me["id"],)).fetchall()
    if tab == "major":
        mine, found = major_words(me["major"]), []
        for u in others:
            if u["major"].strip().lower() == me["major"].strip().lower():
                found.append((0, u, "Same major"))
            elif mine & major_words(u["major"]):
                found.append((1, u, f"Also studies {u['major']}"))
        players = [(u, note) for _, u, note in sorted(found, key=lambda f: f[0])]
    elif tab == "year":
        my_year = YEARS.index(me["year"]) if me["year"] in YEARS else 0
        found = [(abs(YEARS.index(u["year"]) - my_year), u) for u in others if u["year"] in YEARS]
        players = [(u, "Same year" if gap == 0 else u["year"]) for gap, u in sorted(found, key=lambda f: f[0]) if gap <= 1]
    else:
        tab = "online"
        online = sorted((u for u in others if is_online(u)), key=lambda u: u["last_seen"], reverse=True)
        players = [(u, f"{u['major']} · {u['year']}") for u in online]
    return render_template("discover.html", tab=tab, players=players, relations=friend_relations(),
                           studying=who_is_studying())


# --- Clans ------------------------------------------------------------------

@app.route("/clans")
@login_required
def clan_list():
    clans = get_db().execute(CLAN_SELECT + " " + CLAN_GROUP + " ORDER BY xp DESC").fetchall()
    mine = my_clan_ids()
    return render_template(
        "clans.html",
        mine=[c for c in clans if c["id"] in mine],
        others=[c for c in clans if c["id"] not in mine],
    )


@app.route("/clans/new", methods=["GET", "POST"])
@login_required
def clan_new():
    form = request.form
    if request.method == "POST":
        name = form.get("name", "").strip()[:40]
        kind, emblem = form.get("kind"), form.get("emblem")
        if not name:
            flash("Give your clan a name.", "error")
        elif kind not in CLAN_KINDS or emblem not in CLAN_EMBLEMS:
            flash("Pick a clan type and an emblem.", "error")
        else:
            db = get_db()
            try:
                new_id = insert(db,
                    "INSERT INTO clans (name, kind, emblem, description, founder_id) VALUES (?, ?, ?, ?, ?)",
                    (name, kind, emblem, form.get("description", "").strip()[:200], g.user["id"]),
                )
            except db_module.IntegrityError:
                db.rollback()
                flash("A clan with that name already exists.", "error")
            else:
                db.execute(
                    "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (new_id, g.user["id"], now()),
                )
                db.commit()
                flash(f"{name} is founded! Invite your members to join.")
                return redirect(url_for("clan_detail", clan_id=new_id))
    return render_template("clan_new.html", form=form)


@app.route("/clans/<int:clan_id>")
@login_required
def clan_detail(clan_id):
    clan = get_clan(clan_id)
    members = get_db().execute(
        "SELECT u.* FROM clan_members m JOIN users u ON u.id = m.user_id WHERE m.clan_id = ? ORDER BY u.xp DESC",
        (clan_id,),
    ).fetchall()
    return render_template(
        "clan_detail.html", clan=clan, members=members, is_member=any(m["id"] == g.user["id"] for m in members)
    )


@app.post("/clans/<int:clan_id>/join")
@login_required
def join_clan(clan_id):
    clan = get_clan(clan_id)
    db = get_db()
    db.execute(
        "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
        (clan_id, g.user["id"], now()),
    )
    db.commit()
    flash(f"Welcome to {clan['name']}! Your study time, CC, and XP now count toward the clan.")
    return redirect(url_for("clan_detail", clan_id=clan_id))


@app.post("/clans/<int:clan_id>/leave")
@login_required
def leave_clan(clan_id):
    clan = get_clan(clan_id)
    db = get_db()
    db.execute("DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?", (clan_id, g.user["id"]))
    db.execute(  # stop wearing the clan's name as a title
        "UPDATE users SET title = '', title_kind = '' WHERE id = ? AND title_kind = ?", (g.user["id"], f"clan:{clan_id}")
    )
    remaining = db.execute("SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (clan_id,)).fetchone()[0]
    if remaining == 0:
        db.execute("DELETE FROM clans WHERE id = ?", (clan_id,))
        flash(f"You were the last member, so {clan['name']} has been disbanded.")
    else:
        flash(f"You left {clan['name']}.")
    db.commit()
    return redirect(url_for("clan_list"))


# --- Leaderboards -----------------------------------------------------------

@app.route("/leaderboard")
@login_required
def leaderboard():
    board = "clans" if request.args.get("board") == "clans" else "players"
    boards = CLAN_BOARDS if board == "clans" else PLAYER_BOARDS
    metric = request.args.get("metric")
    if metric not in boards:
        metric = next(iter(boards))
    column, label = boards[metric]  # column names come from the dicts above, never from the request
    db = get_db()
    my_rank = None
    if board == "clans":
        mine = my_clan_ids()
        rows = [{"clan": c, "value": c[column], "me": c["id"] in mine}
                for c in db.execute(CLAN_SELECT + " " + CLAN_GROUP + f" ORDER BY {column} DESC, c.name LIMIT 25")]
    else:
        rows = [{"user": u, "value": u[column], "me": u["id"] == g.user["id"]}
                for u in db.execute(f"SELECT * FROM users ORDER BY {column} DESC, name LIMIT 25")]
        my_rank = 1 + db.execute(f"SELECT COUNT(*) FROM users WHERE {column} > ?", (g.user[column],)).fetchone()[0]
    return render_template(
        "leaderboard.html",
        board=board,
        metric=metric,
        label=label,
        tabs=[(key, tab_label) for key, (_, tab_label) in boards.items()],
        rows=rows,
        my_rank=my_rank,
        my_value=g.user[column] if board == "players" else None,
    )


# --- Friends ----------------------------------------------------------------

# --- Chat -------------------------------------------------------------------

def chat_rooms():
    """Rooms the current user can read and post in, grouped for the sidebar.
    Keys: "global", "clan:<id>", "class:<course>", and "dm:<friend's user id>"."""
    db, me = get_db(), g.user["id"]
    rooms = [{"key": "global", "label": "Global", "group": "Everyone"}]
    for clan in db.execute(
        "SELECT c.id, c.name, c.emblem FROM clan_members m JOIN clans c ON c.id = m.clan_id WHERE m.user_id = ? ORDER BY c.name",
        (me,),
    ):
        rooms.append({"key": f"clan:{clan['id']}", "label": f"{clan['emblem']} {clan['name']}", "group": "Clan"})
    for course in parse_courses(g.user["courses"]):
        rooms.append({"key": f"class:{course}", "label": course, "group": "Classes"})
    friends = [uid for uid, status in friend_relations().items() if status == "friends"]
    if friends:
        marks = ",".join("?" * len(friends))
        for friend in db.execute(f"SELECT id, name FROM users WHERE id IN ({marks}) ORDER BY name", friends):
            rooms.append({"key": f"dm:{friend['id']}", "label": friend["name"], "group": "Direct messages"})
    return rooms


def room_channel(key):
    """Where a room's messages are stored. A DM is the same channel from both sides."""
    if key.startswith("dm:"):
        low, high = sorted((g.user["id"], int(key[3:])))
        return f"dm:{low}:{high}"
    return key


def open_room(key):
    """The room for this key if the current user is allowed in it, else 404."""
    room = next((r for r in chat_rooms() if r["key"] == key), None)
    if room is None:
        abort(404)
    return room


def room_messages(key, after=0):
    rows = get_db().execute(
        "SELECT m.id, m.body, m.sent_at, m.user_id, u.name, u.title, u.skin, u.outfit FROM messages m"
        " JOIN users u ON u.id = m.user_id WHERE m.channel = ? AND m.id > ? ORDER BY m.id DESC LIMIT 100",
        (room_channel(key), after),
    ).fetchall()
    return rows[::-1]


@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    key = request.args.get("room", "global")
    room = open_room(key)
    if request.method == "POST":
        body = request.form.get("body", "").strip()[:MAX_MESSAGE_LENGTH]
        if body:
            db = get_db()
            db.execute(
                "INSERT INTO messages (channel, user_id, body, sent_at) VALUES (?, ?, ?, ?)",
                (room_channel(key), g.user["id"], body, now()),
            )
            db.commit()
        return redirect(url_for("chat", room=key))
    messages = room_messages(key)
    return render_template(
        "chat.html", rooms=chat_rooms(), room=room, messages=messages,
        last_id=messages[-1]["id"] if messages else 0, max_length=MAX_MESSAGE_LENGTH,
    )


@app.route("/chat/poll")
@login_required
def chat_poll():
    """New messages since `after`, rendered, for the chat page to append every few seconds."""
    key = request.args.get("room", "global")
    open_room(key)
    messages = room_messages(key, request.args.get("after", 0, type=int))
    return {
        "html": render_template("_messages.html", messages=messages) if messages else "",
        "last_id": messages[-1]["id"] if messages else request.args.get("after", 0, type=int),
    }


@app.route("/friends")
@login_required
def friend_list():
    relations = friend_relations()
    me = g.user["id"]
    users = get_db().execute(
        "SELECT * FROM users WHERE id IN (SELECT friend_id FROM friendships WHERE user_id = ?)"
        " OR id IN (SELECT user_id FROM friendships WHERE friend_id = ?) ORDER BY name",
        (me, me),
    ).fetchall()
    groups = {"friends": [], "received": [], "sent": []}
    for user in users:
        groups[relations[user["id"]]].append(user)
    suggestions = [m for m in find_matches(g.user, limit=20) if m["user"]["id"] not in relations][:6]
    return render_template("friends.html", **groups, suggestions=suggestions, studying=who_is_studying())


@app.post("/friends/<int:user_id>/add")
@login_required
def add_friend(user_id):
    other = get_user(user_id)
    if user_id != g.user["id"]:
        db = get_db()
        db.execute("INSERT INTO friendships (user_id, friend_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (g.user["id"], user_id))
        db.commit()
        if friend_relations().get(user_id) == "friends":
            flash(f"You and {other['name']} are now friends!")
        else:
            flash(f"Friend request sent to {other['name']}.")
    return back("friend_list")


@app.post("/friends/<int:user_id>/remove")
@login_required
def remove_friend(user_id):
    """Unfriend, decline a request, or cancel one you sent."""
    db = get_db()
    db.execute(
        "DELETE FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)",
        (g.user["id"], user_id, user_id, g.user["id"]),
    )
    db.commit()
    flash("Friend list updated.")
    return back("friend_list")


if __name__ == "__main__":
    

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
