"""Sooner Buddies: a campus RPG for OU students where studying together levels you up."""
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

import avatar

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # don't send the login cookie on cross-site form posts
DATABASE = os.path.join(app.root_path, "soonerbuddies.db")

# Only OU addresses can sign up. Set to "" to allow any email (handy for testing).
EMAIL_DOMAIN = "ou.edu"
YEARS = ["Freshman", "Sophomore", "Junior", "Senior", "Graduate"]
GENDERS = ["Prefer not to say", "Female", "Male", "Non-binary", "Other"]
STARTING_CC = 150  # enough for a first item in the avatar shop

# Studying in a dungeon ("fighting") earns rewards per minute.
CC_PER_MINUTE = 1
XP_PER_MINUTE = 2
PARTY_BONUS = 1.5  # when studying with a party of 2+ members
MAX_SESSION_MINUTES = 240  # a forgotten session can't farm rewards forever
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
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.open_resource("schema.sql") as f:
        get_db().executescript(f.read().decode())


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


def fight_rewards(minutes, party_bonus):
    """(CC, XP) earned for a study session."""
    multiplier = PARTY_BONUS if party_bonus else 1
    return round(minutes * CC_PER_MINUTE * multiplier), round(minutes * XP_PER_MINUTE * multiplier)


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
    SELECT p.*, u.name AS leader_name, COUNT(m.user_id) AS member_count
    FROM parties p
    JOIN users u ON u.id = p.leader_id
    LEFT JOIN party_members m ON m.party_id = p.id
"""


def party_info(row):
    """Party row -> dict with its dungeon details and whether it's meeting right now."""
    party = dict(row)
    party["place"] = place(party["dungeon"])
    party["live"] = party["starts_at"] <= now() < party["ends_at"]
    return party


def open_parties(search=""):
    """Parties that haven't ended, soonest first. `search` matches class, name, or dungeon."""
    rows = get_db().execute(
        PARTY_SELECT + " WHERE p.ends_at > ? GROUP BY p.id ORDER BY p.starts_at", (now(),)
    ).fetchall()
    parties = [party_info(row) for row in rows]
    if search:
        text, course = search.lower(), normalize_course(search)
        parties = [p for p in parties
                   if course in p["course"] or text in p["name"].lower() or text in p["place"]["name"].lower()]
    return parties


def get_party(party_id):
    row = get_db().execute(PARTY_SELECT + " WHERE p.id = ? GROUP BY p.id", (party_id,)).fetchone()
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
    flash(f"Clock started at {place(dungeon)['name']}. Hit Finish when you're done studying.")


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
           COALESCE(SUM(u.xp), 0) AS xp,
           COALESCE(SUM(u.cc_earned), 0) AS cc,
           COALESCE(SUM(u.study_minutes), 0) AS study,
           COALESCE(SUM(u.raids), 0) AS raids
    FROM clans c
    LEFT JOIN users f ON f.id = c.founder_id
    LEFT JOIN clan_members m ON m.clan_id = c.id
    LEFT JOIN users u ON u.id = m.user_id
"""


def get_clan(clan_id):
    clan = get_db().execute(CLAN_SELECT + " WHERE c.id = ? GROUP BY c.id", (clan_id,)).fetchone()
    if clan is None:
        abort(404)
    return clan


def my_clan_ids():
    rows = get_db().execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (g.user["id"],)).fetchall()
    return {row["clan_id"] for row in rows}


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


@app.template_global()
def elapsed_seconds(ts):
    return max(0, int((datetime.now() - datetime.fromisoformat(ts)).total_seconds()))


@app.template_global()
def next_field():
    """Hidden input so a form post can send the user back to the page it came from."""
    return Markup(f'<input type="hidden" name="next" value="{escape(request.full_path)}">')


def back(default):
    """Redirect to the form's `next` page if it's on this site, otherwise to `default`."""
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith(("//", "/\\")):
        return redirect(target)
    return redirect(url_for(default))


@app.context_processor
def constants():
    return {
        "years": YEARS, "genders": GENDERS, "dungeons": DUNGEONS, "party_hours": PARTY_HOURS,
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


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def profile_error(form):
    if not (form.get("name", "").strip() and form.get("major", "").strip()):
        return "Please fill in your name and major."
    if form.get("gender") not in GENDERS or form.get("year") not in YEARS:
        return "Please pick your gender and year."
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
    """(name, gender, major, year, courses) from a validated profile form."""
    return (form["name"].strip()[:40], form["gender"], form["major"].strip()[:60], form["year"],
            ", ".join(parse_courses(form["courses"])))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = request.form
    if request.method == "POST":
        error = signup_error(form)
        if not error:
            db = get_db()
            try:
                cur = db.execute(
                    "INSERT INTO users (email, password_hash, cc, name, gender, major, year, courses)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (form["email"].strip().lower(), generate_password_hash(form["password"]), STARTING_CC,
                     *profile_values(form)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                error = "An account with that email already exists."
            else:
                session.clear()
                session["user_id"] = cur.lastrowid
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
            return redirect(url_for("dashboard"))
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
                "UPDATE users SET name = ?, gender = ?, major = ?, year = ?, courses = ? WHERE id = ?",
                (*profile_values(request.form), g.user["id"]),
            )
            db.commit()
            flash("Profile saved.")
            return redirect(url_for("player", user_id=g.user["id"]))
        flash(error, "error")
        return render_template("profile.html", form=request.form)
    return render_template("profile.html", form=dict(g.user))


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
            cur = db.execute(
                "INSERT INTO parties (leader_id, name, course, dungeon, spot, description, capacity, starts_at, ends_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], name, course, dungeon, form.get("spot", "").strip()[:60],
                 form.get("description", "").strip()[:200], capacity,
                 stamp(start), stamp(start + timedelta(hours=hours_open))),
            )
            db.execute(
                "INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
                (cur.lastrowid, g.user["id"], now()),
            )
            db.commit()
            flash("Your party is up! Classmates taking that class will see it first.")
            return redirect(url_for("party_detail", party_id=cur.lastrowid))
    return render_template("party_new.html", form=form)


@app.route("/parties/<int:party_id>")
@login_required
def party_detail(party_id):
    party = get_party(party_id)
    members = get_db().execute(
        "SELECT u.* FROM party_members m JOIN users u ON u.id = m.user_id WHERE m.party_id = ? ORDER BY m.joined_at",
        (party_id,),
    ).fetchall()
    return render_template(
        "party_detail.html",
        party=party,
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
            "INSERT OR IGNORE INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
            (party_id, g.user["id"], now()),
        )
        db.commit()
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
    return redirect(url_for("party_list"))


@app.post("/parties/<int:party_id>/disband")
@login_required
def disband_party(party_id):
    party = get_party(party_id)
    if party["leader_id"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("UPDATE parties SET ends_at = ? WHERE id = ?", (now(), party_id))
    db.commit()
    flash(f"{party['name']} has been disbanded. Good work, everyone!")
    return redirect(url_for("party_list"))


@app.post("/parties/<int:party_id>/study")
@login_required
def party_study(party_id):
    party = get_party(party_id)
    is_member = get_db().execute(
        "SELECT 1 FROM party_members WHERE party_id = ? AND user_id = ?", (party_id, g.user["id"])
    ).fetchone()
    if not is_member:
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
    fighters = Counter(s["dungeon"] for s in who_is_studying().values())
    live = Counter(p["dungeon"] for p in open_parties() if p["live"])
    return render_template("dungeons.html", fighters=fighters, live=live)


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
    cc, xp = fight_rewards(minutes, bonus)
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
        flash(f"Session finished: {minutes} min studied, +{cc} CC, +{xp} XP{' (includes party bonus)' if bonus else ''}.")
        new_level = level_info(g.user["xp"] + xp)["level"]
        if new_level > level_info(g.user["xp"])["level"]:
            flash(f"Level up! You're now level {new_level}.", "level")
    return back("dashboard")


@app.route("/raids")
@login_required
def raids():
    return render_template("raids.html")


# --- Clans ------------------------------------------------------------------

@app.route("/clans")
@login_required
def clan_list():
    clans = get_db().execute(CLAN_SELECT + " GROUP BY c.id ORDER BY xp DESC").fetchall()
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
                cur = db.execute(
                    "INSERT INTO clans (name, kind, emblem, description, founder_id) VALUES (?, ?, ?, ?, ?)",
                    (name, kind, emblem, form.get("description", "").strip()[:200], g.user["id"]),
                )
            except sqlite3.IntegrityError:
                flash("A clan with that name already exists.", "error")
            else:
                db.execute(
                    "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (cur.lastrowid, g.user["id"], now()),
                )
                db.commit()
                flash(f"{name} is founded! Invite your members to join.")
                return redirect(url_for("clan_detail", clan_id=cur.lastrowid))
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
        "INSERT OR IGNORE INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
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
                for c in db.execute(CLAN_SELECT + f" GROUP BY c.id ORDER BY {column} DESC, c.name LIMIT 25")]
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
        db.execute("INSERT OR IGNORE INTO friendships (user_id, friend_id) VALUES (?, ?)", (g.user["id"], user_id))
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
    app.run(debug=True)
