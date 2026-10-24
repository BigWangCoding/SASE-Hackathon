# Sooner Study Buddy

A study buddy website for University of Oklahoma students. It shows where classmates are
studying right now, down to the building and room number, so nobody has to study alone.

## What it does

- **Profiles:** sign up with an `@ou.edu` email, then add your name, major, year, and classes.
- **Find a room:** browse every open study room, or search by class (`CHEM`, `CS 2413`),
  topic, or building (`Bizzell`). Join with one click.
- **Post a room:** already studying? Post the class, building, room, how long you'll be
  there, and how many people can join. Classmates in that class will see it on their dashboard.
- **Matching:** your dashboard shows open rooms for your exact classes first, then rooms in the
  same department (CHEM 1315 → CHEM 3053). It also lists the students most like you, ranked by
  shared classes, shared departments, and major, and shows if they're studying somewhere right now.

Rooms close on their own when their time runs out, and a host can end a session early.

## Run it

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python seed.py        # optional: loads demo students and rooms (wipes existing data)
python app.py
```

Then open http://127.0.0.1:5000.

With the demo data, log in as **demo@ou.edu** / **password123**. Every seeded student uses the
same password (for example `ava@ou.edu`), so you can open a second browser window and join
rooms as someone else.

To let any email sign up while testing, set `EMAIL_DOMAIN = ""` in `app.py`.

## How it's built

| File | Purpose |
| --- | --- |
| `app.py` | Flask app: routes, login, matching, and room logic |
| `schema.sql` | SQLite tables (`users`, `rooms`, `room_members`), created automatically on startup |
| `seed.py` | Demo data for presentations |
| `templates/` | Jinja HTML pages |
| `static/style.css` | Styling |

Data is stored in `studybuddy.db` (SQLite, git-ignored). There is no JavaScript and no build step.

## Ideas for next steps

- Schedule rooms in advance ("Chem study group tonight at 7")
- Show rooms on a campus map
- In-room chat, or a "running late" note to the host
- Email verification for `@ou.edu` accounts
- CSRF protection and a real `SECRET_KEY` before deploying publicly
