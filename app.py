"""Sooner Study Buddy: find (or post) study rooms and classmates at OU."""
import os
import re
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
DATABASE = os.path.join(app.root_path, "studybuddy.db")

# Only OU addresses can sign up. Set to "" to allow any email (handy for testing).
EMAIL_DOMAIN = "ou.edu"
YEARS = ["Freshman", "Sophomore", "Junior", "Senior", "Graduate"]
DURATIONS = [1, 2, 3, 4]  # hours a posted room stays open
BUILDINGS = [
    "Bizzell Memorial Library",
    "Oklahoma Memorial Union",
    "Physical Sciences Center",
    "Devon Energy Hall",
    "Gallogly Hall",
    "Carson Engineering Center",
    "Felgar Hall",
    "Sarkeys Energy Center",
    "Dale Hall",
    "Adams Hall",
    "Price Hall",
    "Gaylord Hall",
    "Kaufman Hall",
    "Wagner Hall",
]


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
        shared = mine & theirs
        shared_depts = my_depts & {department(c) for c in theirs}
        same_major = other["major"].strip().lower() == me["major"].strip().lower()
        score = 3 * len(shared) + len(shared_depts) + (2 if same_major else 0)
        if score:
            matches.append({
                "user": other,
                "shared": sorted(shared),
                "other_depts": sorted(shared_depts - {department(c) for c in shared}),
                "same_major": same_major,
                "score": score,
            })
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:limit]


# --- Rooms ------------------------------------------------------------------

ROOM_SELECT = """
    SELECT r.*, u.name AS host_name, COUNT(m.user_id) AS member_count
    FROM rooms r
    JOIN users u ON u.id = r.host_id
    LEFT JOIN room_members m ON m.room_id = r.id
"""


def active_rooms(search=""):
    sql = ROOM_SELECT + " WHERE r.ends_at > ?"
    args = [now()]
    if search:
        like = f"%{normalize_course(search)}%"
        sql += " AND (r.course LIKE ? OR r.topic LIKE ? OR r.building LIKE ?)"
        args += [like, like, like]
    sql += " GROUP BY r.id ORDER BY r.ends_at"
    return get_db().execute(sql, args).fetchall()


def get_room(room_id):
    room = get_db().execute(ROOM_SELECT + " WHERE r.id = ? GROUP BY r.id", (room_id,)).fetchone()
    if room is None:
        abort(404)
    return room


def rooms_for_user(user, rooms):
    """Rooms for the user's exact classes first, then rooms in the same departments."""
    mine = set(parse_courses(user["courses"]))
    depts = {department(c) for c in mine}
    exact = [r for r in rooms if r["course"] in mine]
    related = [r for r in rooms if r["course"] not in mine and department(r["course"]) in depts]
    return exact + related


def my_room_ids():
    rows = get_db().execute(
        "SELECT m.room_id FROM room_members m JOIN rooms r ON r.id = m.room_id"
        " WHERE m.user_id = ? AND r.ends_at > ?",
        (g.user["id"], now()),
    ).fetchall()
    return {row["room_id"] for row in rows}


def who_is_studying():
    """Map of user id -> the open room they're currently in."""
    rows = get_db().execute(
        "SELECT m.user_id, r.id, r.course, r.building, r.room_number"
        " FROM room_members m JOIN rooms r ON r.id = m.room_id WHERE r.ends_at > ?",
        (now(),),
    ).fetchall()
    return {row["user_id"]: row for row in rows}


# --- Template helpers -------------------------------------------------------

app.add_template_filter(parse_courses, "courses")


@app.template_filter("clock")
def clock(ts):
    return datetime.fromisoformat(ts).strftime("%I:%M %p").lstrip("0")


@app.template_filter("time_left")
def time_left(ts):
    minutes = int((datetime.fromisoformat(ts) - datetime.now()).total_seconds() // 60)
    if minutes <= 0:
        return "ended"
    if minutes < 60:
        return f"{minutes} min left"
    return f"{minutes // 60}h {minutes % 60}m left"


@app.context_processor
def constants():
    return {"years": YEARS, "buildings": BUILDINGS, "durations": DURATIONS}


# --- Auth -------------------------------------------------------------------

@app.before_request
def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


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
    if form.get("year") not in YEARS:
        return "Please pick your year."
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


@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = request.form
    if request.method == "POST":
        error = signup_error(form)
        if not error:
            db = get_db()
            try:
                cur = db.execute(
                    "INSERT INTO users (name, email, password_hash, major, year, courses)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (form["name"].strip(), form["email"].strip().lower(),
                     generate_password_hash(form["password"]), form["major"].strip(),
                     form["year"], ", ".join(parse_courses(form["courses"]))),
                )
                db.commit()
            except sqlite3.IntegrityError:
                error = "An account with that email already exists."
            else:
                session.clear()
                session["user_id"] = cur.lastrowid
                flash("Welcome! Here are open rooms and classmates that match your classes.")
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


# --- Pages ------------------------------------------------------------------

@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("index.html", open_count=len(active_rooms()))


@app.route("/dashboard")
@login_required
def dashboard():
    rooms = active_rooms()
    mine = my_room_ids()
    return render_template(
        "dashboard.html",
        my_rooms=[r for r in rooms if r["id"] in mine],
        suggested=[r for r in rooms_for_user(g.user, rooms) if r["id"] not in mine],
        matches=find_matches(g.user),
        studying_now=who_is_studying(),
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        form = request.form
        error = profile_error(form)
        if not error:
            db = get_db()
            db.execute(
                "UPDATE users SET name = ?, major = ?, year = ?, courses = ? WHERE id = ?",
                (form["name"].strip(), form["major"].strip(), form["year"],
                 ", ".join(parse_courses(form["courses"])), g.user["id"]),
            )
            db.commit()
            flash("Profile saved.")
            return redirect(url_for("dashboard"))
        flash(error, "error")
        return render_template("profile.html", form=form)
    return render_template("profile.html", form=dict(g.user))


@app.route("/rooms")
@login_required
def rooms():
    q = request.args.get("q", "").strip()
    return render_template("rooms.html", rooms=active_rooms(q), q=q, my_room_ids=my_room_ids())


@app.route("/rooms/new", methods=["GET", "POST"])
@login_required
def new_room():
    form = request.form
    if request.method == "POST":
        course = normalize_course(form.get("course", ""))
        building = form.get("building", "").strip()
        room_number = form.get("room_number", "").strip()
        hours = form.get("hours", type=int)
        capacity = form.get("capacity", type=int)
        if not (course and building and room_number):
            flash("Class, building, and room are required.", "error")
        elif hours not in DURATIONS or not 2 <= (capacity or 0) <= 30:
            flash("Pick a valid duration and a group size from 2 to 30.", "error")
        else:
            start = datetime.now()
            db = get_db()
            cur = db.execute(
                "INSERT INTO rooms (host_id, course, topic, building, room_number, capacity,"
                " starts_at, ends_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], course, form.get("topic", "").strip(), building, room_number,
                 capacity, stamp(start), stamp(start + timedelta(hours=hours))),
            )
            db.execute(
                "INSERT INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
                (cur.lastrowid, g.user["id"], stamp(start)),
            )
            db.commit()
            flash("Your room is live! Classmates can now find and join you.")
            return redirect(url_for("room_detail", room_id=cur.lastrowid))
    return render_template("room_new.html", form=form)


@app.route("/rooms/<int:room_id>")
@login_required
def room_detail(room_id):
    room = get_room(room_id)
    members = get_db().execute(
        "SELECT u.* FROM room_members m JOIN users u ON u.id = m.user_id"
        " WHERE m.room_id = ? ORDER BY m.joined_at",
        (room_id,),
    ).fetchall()
    return render_template(
        "room_detail.html",
        room=room,
        members=members,
        is_member=any(m["id"] == g.user["id"] for m in members),
        is_host=room["host_id"] == g.user["id"],
        active=room["ends_at"] > now(),
    )


@app.post("/rooms/<int:room_id>/join")
@login_required
def join_room(room_id):
    room = get_room(room_id)
    if room["ends_at"] <= now():
        flash("That session has already ended.", "error")
    elif room["member_count"] >= room["capacity"]:
        flash("Sorry, that room is full.", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
            (room_id, g.user["id"], now()),
        )
        db.commit()
        flash(f"You're in! Head to {room['building']}, {room['room_number']}.")
    return redirect(url_for("room_detail", room_id=room_id))


@app.post("/rooms/<int:room_id>/leave")
@login_required
def leave_room(room_id):
    room = get_room(room_id)
    if room["host_id"] == g.user["id"]:
        flash("You're the host, so end the session instead.", "error")
        return redirect(url_for("room_detail", room_id=room_id))
    db = get_db()
    db.execute("DELETE FROM room_members WHERE room_id = ? AND user_id = ?", (room_id, g.user["id"]))
    db.commit()
    flash("You left the room.")
    return redirect(url_for("dashboard"))


@app.post("/rooms/<int:room_id>/end")
@login_required
def end_room(room_id):
    room = get_room(room_id)
    if room["host_id"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("UPDATE rooms SET ends_at = ? WHERE id = ?", (now(), room_id))
    db.commit()
    flash("Session ended. Nice work!")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
