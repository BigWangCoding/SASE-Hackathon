"""Fill the database with demo adventurers, clans, and parties. WIPES existing data.

    python seed.py

Every demo account uses the password "password123". Log in as demo@ou.edu to see
the app from a new player's point of view.
"""
import json
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

import avatar
import raids as raid_feed
from app import app, get_db, stamp

PASSWORD = "password123"

STUDENTS = [
    # name, email, gender, major, year, classes, skin tone, (xp, cc, cc_earned, study minutes, raids), items worn
    ("Alex Morgan", "demo@ou.edu", "Prefer not to say", "Chemistry", "Freshman",
     "CHEM 1315, MATH 1914, ENGL 1113, BIOL 1124", 1, (1650, 950, 1100, 760, 3), ["hat_cap"]),
    ("Maya Patel", "maya@ou.edu", "Female", "Chemistry", "Sophomore",
     "CHEM 3053, BIOL 1124, MATH 2924", 2, (9800, 640, 4900, 4300, 12),
     ["hair_waves", "shirt_labcoat", "glasses_round", "acc_pendant"]),
    ("Sam Rivera", "sam@ou.edu", "Male", "Biochemistry", "Sophomore",
     "CHEM 3053, CHEM 1415, BIOL 1124", 3, (7200, 300, 3600, 3500, 8),
     ["hair_curls", "shirt_hoodie", "acc_headphones"]),
    ("Ava Johnson", "ava@ou.edu", "Female", "Mechanical Engineering", "Freshman",
     "CHEM 1315, MATH 1914, ENGL 1113", 0, (4100, 220, 2050, 1900, 15),
     ["hair_buns", "shirt_jersey", "shoes_hightops"]),
    ("Emma Davis", "emma@ou.edu", "Female", "Psychology", "Freshman",
     "PSY 1113, ENGL 1113, CHEM 1315", 1, (2600, 410, 1300, 1250, 6),
     ["hair_bob", "glasses_heart", "shirt_flannel"]),
    ("Jordan Lee", "jordan@ou.edu", "Male", "Computer Science", "Junior",
     "CS 2413, MATH 2924, PHYS 2514", 2, (15800, 1200, 7900, 6900, 21),
     ["hair_spikes", "glasses_pixel", "shirt_varsity", "pants_joggers", "shoes_gold"]),
    ("Noah Kim", "noah@ou.edu", "Male", "Computer Science", "Sophomore",
     "CS 2334, CS 2413, MATH 1914", 1, (6100, 150, 3050, 2950, 4),
     ["hair_swoop", "glasses_aviator", "acc_backpack"]),
    ("Liam Brown", "liam@ou.edu", "Male", "Economics", "Senior",
     "ECON 1113, MATH 1743", 3, (12400, 900, 6200, 3100, 34),
     ["hat_cowboy", "shirt_flannel", "pants_khakis", "shoes_boots"]),
    ("Olivia Martinez", "olivia@ou.edu", "Female", "Biology", "Junior",
     "BIOL 1124, CHEM 1415, PSY 1113", 4, (21400, 2100, 10500, 8800, 18),
     ["hair_waves", "hat_crown", "shirt_robe", "acc_cape"]),
    ("Riley Chen", "riley@ou.edu", "Non-binary", "Aerospace Engineering", "Junior",
     "PHYS 2514, MATH 2924, AME 2533", 0, (18300, 700, 9100, 7600, 27),
     ["hair_mohawk", "shirt_jersey", "pants_gold", "acc_shield"]),
    ("Taylor Brooks", "taylor@ou.edu", "Prefer not to say", "Business", "Senior",
     "ECON 1113, MIS 2113, ACCT 2113", 2, (8900, 1500, 4450, 2600, 40),
     ["hat_grad", "shirt_varsity", "acc_scarf"]),
    ("Casey Nguyen", "casey@ou.edu", "Female", "Psychology", "Sophomore",
     "PSY 1113, BIOL 1124, ENGL 1213", 1, (3300, 380, 1650, 1500, 9),
     ["hat_beanie", "pants_shorts", "acc_book"]),
]

# (user, friend) pairs. Both directions = friends; one direction = a pending request.
FRIENDSHIPS = [
    ("demo", "ava"), ("ava", "demo"), ("demo", "maya"), ("maya", "demo"),
    ("emma", "demo"),  # Emma's request is waiting for the demo user to accept
    ("demo", "noah"),  # the demo user's request is waiting on Noah
    ("jordan", "noah"), ("noah", "jordan"), ("maya", "sam"), ("sam", "maya"),
    ("olivia", "casey"), ("casey", "olivia"), ("liam", "taylor"), ("taylor", "liam"),
]

CLANS = [
    # name, type, emblem, description, founder, members
    ("Crimson Chemistry Club", "Club", "🔬", "Lab partners, study groups, and the occasional explosion.",
     "maya", ["maya", "sam", "olivia", "demo"]),
    ("Code Crusaders", "Club", "⚔️", "Programmers who debug together and ship together.",
     "jordan", ["jordan", "noah", "riley"]),
    ("Delta Study Society", "Sorority", "⭐", "Sisterhood built on academics and friendship. (Sample org)",
     "ava", ["ava", "emma", "casey", "olivia"]),
    ("Sigma Scholars", "Fraternity", "🛡️", "Brothers who hold each other to a higher GPA. (Sample org)",
     "liam", ["liam", "sam", "noah", "taylor"]),
    ("Sooner Engineers Guild", "Academic", "⚙️", "Engineers of every discipline building study habits.",
     "riley", ["riley", "ava", "jordan"]),
    ("Pre-Health Society", "Academic", "🎓", "Future doctors, nurses, and pharmacists studying side by side.",
     "olivia", ["olivia", "maya", "casey"]),
]

# Party start times are minutes from now (negative = already meeting).
PARTIES = [
    # leader, name, class, dungeon, spot, description, capacity, start, hours, members
    ("ava", "Gen Chem Grind", "CHEM 1315", "psc", "Room 201",
     "Working through homework 6: stoichiometry.", 6, -25, 2, ["emma"]),
    ("maya", "Orgo Survival Squad", "CHEM 3053", "bizzell", "Group study room 2",
     "Exam 2 review: reaction mechanisms.", 8, -40, 3, ["sam", "olivia"]),
    ("jordan", "Late-Night Code Guild", "CS 2413", "gallogly", "2nd floor lab",
     "Debugging project 3 (linked lists).", 5, -15, 3, ["noah"]),
    ("olivia", "Bio Lab Practical Prep", "BIOL 1124", "bizzell", "3rd floor, table 12",
     "Quizzing each other on the lab practical.", 6, 120, 2, ["casey"]),
    ("riley", "Calc III Problem Set", "MATH 2924", "rawl", "Main floor tables",
     "Problem set 7, then practice exam.", 5, 240, 2, []),
    ("liam", "Econ Midterm Flashcards", "ECON 1113", "union", "2nd floor lounge",
     "Supply, demand, and a lot of flashcards.", 4, 24 * 60, 2, ["taylor"]),
]

# Who is in the middle of a study session right now: (user, party index or None, dungeon, minutes ago).
ACTIVE_SESSIONS = [
    ("ava", 0, "psc", 25), ("emma", 0, "psc", 20),
    ("maya", 1, "bizzell", 40), ("sam", 1, "bizzell", 35),
    ("jordan", 2, "gallogly", 15), ("noah", 2, "gallogly", 12),
    ("taylor", None, "price", 50),
]

# Finished runs for the demo user's history: (dungeon, minutes, with party?, days ago).
DEMO_RUNS = [("bizzell", 45, False, 1), ("psc", 60, True, 2), ("union", 30, False, 3)]

# Raid parties for real upcoming events, matched to the SoonerSports.com feed at seed time:
# (sport slug, home games only?, leader, name, meeting spot, description, members).
RAID_PARTIES = [
    ("football", False, "jordan", "Union watch party", "Oklahoma Memorial Union, 2nd floor TVs",
     "Big screen, snacks, and the whole game.", ["noah", "liam"]),
    ("football", True, "ava", "Student section crew", "South end zone, Gate 7",
     "Meeting early to get seats together. Wear crimson.", ["emma", "casey"]),
    ("mbball", True, "riley", "Lloyd Noble crew", "Lloyd Noble Center main entrance",
     "Going straight from the library.", ["sam"]),
    ("wbball", True, "olivia", "Women's hoops night", "Lloyd Noble Center main entrance", "", ["maya", "taylor"]),
]


def handle(email):
    return email.split("@")[0]


with app.app_context():
    db = get_db()
    db.executescript(
        "DELETE FROM study_sessions; DELETE FROM party_members; DELETE FROM parties;"
        "DELETE FROM clan_members; DELETE FROM clans; DELETE FROM friendships;"
        "DELETE FROM inventory; DELETE FROM raid_checkins; DELETE FROM users;"
    )
    right_now = datetime.now().replace(second=0, microsecond=0)
    password_hash = generate_password_hash(PASSWORD)

    ids = {}
    for name, email, gender, major, year, courses, skin, stats, items in STUDENTS:
        xp, cc, cc_earned, study_minutes, raids = stats
        outfit = {avatar.ITEMS[item_id]["slot"]: item_id for item_id in items}
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, gender, major, year, courses, cc, cc_earned, xp,"
            " study_minutes, raids, skin, outfit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, email, password_hash, gender, major, year, courses, cc, cc_earned, xp,
             study_minutes, raids, avatar.SKIN_TONES[skin], json.dumps(outfit)),
        )
        ids[handle(email)] = cur.lastrowid
        db.executemany(
            "INSERT INTO inventory (user_id, item_id) VALUES (?, ?)", [(cur.lastrowid, item_id) for item_id in items]
        )

    db.executemany(
        "INSERT INTO friendships (user_id, friend_id) VALUES (?, ?)", [(ids[a], ids[b]) for a, b in FRIENDSHIPS]
    )

    for name, kind, emblem, description, founder, members in CLANS:
        cur = db.execute(
            "INSERT INTO clans (name, kind, emblem, description, founder_id) VALUES (?, ?, ?, ?, ?)",
            (name, kind, emblem, description, ids[founder]),
        )
        db.executemany(
            "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
            [(cur.lastrowid, ids[m], stamp(right_now - timedelta(days=30))) for m in members],
        )

    party_ids = []
    for leader, name, course, dungeon, spot, description, capacity, start, hours_open, members in PARTIES:
        starts = right_now + timedelta(minutes=start)
        cur = db.execute(
            "INSERT INTO parties (leader_id, name, course, dungeon, spot, description, capacity, starts_at, ends_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ids[leader], name, course, dungeon, spot, description, capacity,
             stamp(starts), stamp(starts + timedelta(hours=hours_open))),
        )
        party_ids.append(cur.lastrowid)
        db.executemany(
            "INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
            [(cur.lastrowid, ids[m], stamp(right_now - timedelta(hours=1))) for m in [leader, *members]],
        )

    for who, party, dungeon, minutes_ago in ACTIVE_SESSIONS:
        db.execute(
            "INSERT INTO study_sessions (user_id, dungeon, party_id, started_at) VALUES (?, ?, ?, ?)",
            (ids[who], dungeon, None if party is None else party_ids[party],
             stamp(datetime.now() - timedelta(minutes=minutes_ago))),
        )

    for dungeon, minutes, with_party, days_ago in DEMO_RUNS:
        ended = right_now - timedelta(days=days_ago)
        bonus = 1.5 if with_party else 1
        db.execute(
            "INSERT INTO study_sessions (user_id, dungeon, started_at, ended_at, minutes, cc, xp)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ids["demo"], dungeon, stamp(ended - timedelta(minutes=minutes)), stamp(ended), minutes,
             round(minutes * bonus), round(minutes * 2 * bonus)),
        )
    db.commit()

    try:
        raid_feed.sync(db)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Couldn't reach SoonerSports.com ({exc}). Using any raids already saved.")
    raid_party_count = 0
    for slug, home_only, leader, name, spot, description, members in RAID_PARTIES:
        raid = db.execute(
            "SELECT * FROM raids WHERE sport_slug = ? AND ends_at > ?" + (" AND home_away = 'H'" if home_only else "")
            + " ORDER BY starts_at LIMIT 1",
            (slug, stamp(datetime.now())),
        ).fetchone()
        if raid is None:
            continue
        start = datetime.fromisoformat(raid["starts_at"])
        meet = start - timedelta(hours=1) if start.hour else start.replace(hour=12)
        cur = db.execute(
            "INSERT INTO parties (leader_id, name, course, dungeon, spot, description, capacity, starts_at, ends_at, raid_id)"
            " VALUES (?, ?, ?, 'other', ?, ?, 10, ?, ?, ?)",
            (ids[leader], name, raid["sport"], spot, description, stamp(meet), raid["ends_at"], raid["id"]),
        )
        db.executemany(
            "INSERT INTO party_members (party_id, user_id, joined_at) VALUES (?, ?, ?)",
            [(cur.lastrowid, ids[m], stamp(right_now - timedelta(hours=2))) for m in [leader, *members]],
        )
        raid_party_count += 1
    db.commit()

print(f"Seeded {len(STUDENTS)} adventurers, {len(CLANS)} clans, {len(PARTIES)} parties, "
      f"and {raid_party_count} raid parties.")
print(f"Log in as demo@ou.edu / {PASSWORD}")
