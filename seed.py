"""Fill the database with demo students and open study rooms. WIPES existing data.

    python seed.py

Every demo account uses the password "password123". Log in as demo@ou.edu
to see the app from a new student's point of view.
"""
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import app, get_db, stamp

PASSWORD = "password123"

STUDENTS = [
    # name, email, major, year, classes
    ("Alex Morgan", "demo@ou.edu", "Chemistry", "Freshman", "CHEM 1315, MATH 1914, ENGL 1113, BIOL 1124"),
    ("Maya Patel", "maya@ou.edu", "Chemistry", "Sophomore", "CHEM 3053, BIOL 1124, MATH 2924"),
    ("Sam Rivera", "sam@ou.edu", "Biochemistry", "Sophomore", "CHEM 3053, CHEM 1415, BIOL 1124"),
    ("Ava Johnson", "ava@ou.edu", "Mechanical Engineering", "Freshman", "CHEM 1315, MATH 1914, ENGL 1113"),
    ("Emma Davis", "emma@ou.edu", "Psychology", "Freshman", "PSY 1113, ENGL 1113, CHEM 1315"),
    ("Jordan Lee", "jordan@ou.edu", "Computer Science", "Junior", "CS 2413, MATH 2924, PHYS 2514"),
    ("Noah Kim", "noah@ou.edu", "Computer Science", "Sophomore", "CS 2334, CS 2413, MATH 1914"),
    ("Liam Brown", "liam@ou.edu", "Economics", "Senior", "ECON 1113, MATH 1743"),
    ("Olivia Martinez", "olivia@ou.edu", "Biology", "Junior", "BIOL 1124, CHEM 1415, PSY 1113"),
]

ROOMS = [
    # host, class, topic, building, room, capacity, hours open, other members
    ("ava@ou.edu", "CHEM 1315", "Homework 6: stoichiometry", "Physical Sciences Center", "Room 201", 6, 2, ["emma@ou.edu"]),
    ("maya@ou.edu", "CHEM 3053", "Orgo exam 2 review: reaction mechanisms", "Bizzell Memorial Library", "LL118", 8, 3, ["sam@ou.edu"]),
    ("olivia@ou.edu", "BIOL 1124", "Lab practical prep", "Bizzell Memorial Library", "3rd floor, table 12", 6, 2, []),
    ("jordan@ou.edu", "CS 2413", "Debugging project 3 (linked lists)", "Devon Energy Hall", "Room 270", 5, 2, ["noah@ou.edu"]),
    ("liam@ou.edu", "ECON 1113", "Midterm flashcards", "Oklahoma Memorial Union", "2nd floor lounge", 4, 1, []),
]

with app.app_context():
    db = get_db()
    db.executescript("DELETE FROM room_members; DELETE FROM rooms; DELETE FROM users;")

    password_hash = generate_password_hash(PASSWORD)
    ids = {}
    for name, email, major, year, courses in STUDENTS:
        cur = db.execute(
            "INSERT INTO users (name, email, password_hash, major, year, courses) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, password_hash, major, year, courses),
        )
        ids[email] = cur.lastrowid

    start = datetime.now() - timedelta(minutes=20)
    for host, course, topic, building, room_number, capacity, hours, members in ROOMS:
        cur = db.execute(
            "INSERT INTO rooms (host_id, course, topic, building, room_number, capacity, starts_at, ends_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ids[host], course, topic, building, room_number, capacity,
             stamp(start), stamp(start + timedelta(hours=hours))),
        )
        for email in [host, *members]:
            db.execute(
                "INSERT INTO room_members (room_id, user_id, joined_at) VALUES (?, ?, ?)",
                (cur.lastrowid, ids[email], stamp(start)),
            )
    db.commit()

print(f"Seeded {len(STUDENTS)} students and {len(ROOMS)} open rooms.")
print(f"Log in as demo@ou.edu / {PASSWORD}")
