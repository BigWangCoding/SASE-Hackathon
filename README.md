# Sooner Buddies

A campus RPG for University of Oklahoma students that turns studying together into a game.
Students form **parties** (study groups), meet up in **study dungeons** (real study spots on
campus), and earn **Crimson Crystals (CC)** and **XP** for every minute they study.

## Features

- **Character profile:** name, gender, major, year, classes, CC, and XP/level.
- **Avatar forge & shop:** spend CC on hair, hats, eyewear, shirts, pants, shoes, and
  accessories. Every item is drawn onto your avatar, and the shop previews each item on you
  before you buy it.
- **Parties:** create or join a study party for a class at a dungeon, now or later. Classmates
  in the same class (or department) see your party first.
- **Study dungeons:** Bizzell, the Union, computer labs, and more. Start a session ("fight")
  solo or with your party, then hit *Finish* to claim rewards:
  - 1 CC + 2 XP per minute, capped at 4 hours per session
  - +50% when studying with a party of 2+
- **Stats:** level, CC, time studying, raids attended, friends, clans, and recent dungeon runs.
- **Friends:** send and accept friend requests, and see when friends are studying.
  The app suggests classmates who share your classes.
- **Clans:** clubs, fraternities, sororities, and other orgs. A clan's XP, CC, study time,
  and raids are the totals of its members' stats.
- **Leaderboards:**
  - *Players:* highest level, most CC, most raids, most study time
  - *Clans:* most CC, most raids, most study time

  Leaderboards rank by CC *earned*, so spending CC in the shop never drops anyone down a board.
- **Campus raids (coming soon):** events pulled from OU Engage. For now there's a placeholder
  page, and each player has a `raids` stat ready to be filled in.

## Run it

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python seed.py        # optional: demo players, clans, and live parties (wipes existing data)
python app.py
```

Then open http://127.0.0.1:5000 and log in as **demo@ou.edu** / **password123**. Every seeded
player uses the same password (for example `maya@ou.edu`), so you can open a second browser
window to accept friend requests or join parties as someone else.

**Live demo tip:** studying earns rewards in real minutes, which is slow on stage. Start the app with

```bash
DEMO_TIME_SCALE=60 python app.py          # macOS/Linux
$env:DEMO_TIME_SCALE=60; python app.py    # Windows PowerShell
```

and each real second counts as one study minute.

To let any email sign up while testing, set `EMAIL_DOMAIN = ""` in `app.py`.

## How it's built

Flask + SQLite, server-rendered HTML. No build step, and the only JavaScript is the live
session timer.

| File | Purpose |
| --- | --- |
| `app.py` | Routes and game rules: rewards, levels, parties, dungeons, clans, friends, leaderboards |
| `avatar.py` | Avatar shop items and the SVG avatar renderer |
| `schema.sql` | Database tables, created automatically on startup |
| `seed.py` | Demo data for presentations |
| `templates/` | Jinja HTML pages |
| `static/style.css` | OU crimson and cream theme |

Data is stored in `soonerbuddies.db` (git-ignored). The list of dungeons is `DUNGEONS` in
`app.py`, and reward rates are the constants at the top of the same file.

## Next steps

- Pull campus events from OU Engage as raids, with raid parties and check-in rewards
- Verify study sessions (e.g. location check-in) so rewards can't be faked
- Email verification for `@ou.edu` accounts
- CSRF tokens and a real `SECRET_KEY` before deploying publicly
