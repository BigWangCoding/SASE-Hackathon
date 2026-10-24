# Sooner Buddies

A campus RPG for University of Oklahoma students that turns studying together into a game.
Students form **parties** (study groups), clear **dungeon rooms** (real study spots on campus),
go on **raids** (OU games and events), and earn **Crimson Crystals (CC)** and **XP** as loot.

| Game term | What it means |
| --- | --- |
| Dungeon room | A study spot on campus (Bizzell, the Union, computer labs...) |
| Dungeon run | A study session; clearing it pays out loot |
| Party | A study group |
| Raid / raid party | An OU athletics event / a group going to it (or a watch party) |
| Clan | A club, fraternity, sorority, or other org |
| Loot | CC and XP rewards |

## Features

- **Character profile:** name, role (student, professor, faculty, staff), gender, major, year,
  classes, CC, and XP/level.
- **Titles:** wear a title in front of your name everywhere it appears, like chat, parties, and
  leaderboards. The choices are your year (students), Prof./Faculty/Staff, or the name of any clan
  you're in.
- **Chat:** a Global room, a private room for each clan you're in, a room for each class on your
  profile, and direct messages with friends. New messages show up every few seconds.
- **Pet summons:** spend 100 CC to summon an Oklahoma animal (state animal, bird, reptile,
  insect, and more). Your active pet boosts CC or XP from dungeon runs and raids:
  Common +3% (60%), Rare +6% (28%), Epic +10% (10%), Legendary +20% (2%). The legendaries are
  **Boomer** and **Sooner**, the Sooner Schooner ponies. A Legendary is guaranteed within 50
  summons, and duplicates refund 25 CC. The catalog is in `pets.py`.
- **Avatar forge & shop:** spend CC on hair, hats, eyewear, shirts, pants, shoes, and
  accessories. Every item is drawn onto your avatar, and the shop previews each item on you
  before you buy it.
- **Parties:** create or join a study party for a class at a dungeon, now or later. Classmates
  in the same class (or department) see your party first.
- **Dungeon rooms:** Bizzell, the Union, computer labs, and more, each with an illustrated icon of
  the spot. Click the icon to see who's inside (avatars with their pets). Start a dungeon run solo
  or with your party, then clear it to collect loot:
  - 1 CC + 2 XP per minute, capped at 4 hours per session
  - +50% when studying with a party of 2+
- **QR codes:** every dungeon room and raid has a printable QR code (`/qr/...`) to post at the spot.
  Scanning a dungeon's code starts a dungeon run there. Scanning a raid's code on game day checks
  you in, even without a raid party. Use a phone camera or the in-app **Scan** page. Each code
  carries a signed token, so scan links can't be made up.
- **Campus map:** the real OU campus (OpenStreetMap) with its boundary outlined. Each dungeon room
  has a marker with how many players are inside. Smaller markers show raids on campus this week
  with how many are going. Click a marker to see the players and their pets.
- **Discover:** tabs for players online now (active in the last 5 minutes), similar majors, and
  similar years, plus your friends list.
- **Stats:** level, CC, time studying, raids attended, friends, clans, and recent dungeon runs.
- **Friends:** send and accept friend requests, and see when friends are studying.
  The app suggests classmates who share your classes.
- **Clans:** clubs, fraternities, sororities, and other orgs. A clan's XP, CC, study time,
  and raids are the totals of its members' stats.
- **Leaderboards:**
  - *Players:* highest level, most CC, most raids, most study time
  - *Clans:* most CC, most raids, most study time

  Leaderboards rank by CC *earned*, so spending CC in the shop never drops anyone down a board.
- **Raids:** every OU game and meet from the [SoonerSports.com calendar](https://soonersports.com/calendar),
  with time, location, TV, ticket links, and a short description. Students start or join a
  **raid party** for an event, choosing a meeting spot and time. For away games this is a watch
  party. On game day, raid party members check in for 50 CC + 100 XP (+50% with 2+ in the party),
  which also counts toward their raids stat. Click a raid's icon to see who's going.
- **Student raids and boosting:** anyone can create a raid at a campus place, such as a tailgate,
  watch party, club event, or study jam. They lead its first raid party. The creator can spend
  150 CC to **boost** it, which pins it to the top of the Raids tab for 24 hours. Boosts stack up
  to the end of the raid.

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

## Deploy it with a Supabase database (live demo)

All data (accounts, CC, pets, chat, clans, parties, raids) is stored in the team's Supabase
project. Nothing is pre-filled: the data is whoever signs up.

### Where the data goes

- **Database:** Supabase project `qeqrzsszxdkbcgusbtgh`, inside its own schema, **`sooner_buddies`**.
  The static `index.html` version's tables stay in `public`, untouched. In Supabase's
  **Table Editor**, pick `sooner_buddies` from the schema dropdown to see the data.
- **Connection:** the app connects through the **Session pooler**
  (`aws-1-us-west-2.pooler.supabase.com:5432`). The direct `db.<ref>.supabase.co` address is
  IPv6-only, and Render can't reach it.
- **The password lives in `.env`**, a local file git ignores. The app loads it automatically, so
  `python app.py` on your laptop reads and writes the live Supabase database. To work offline
  against a local SQLite file instead, set `DATABASE_URL` to an empty value
  (PowerShell: `$env:DATABASE_URL=""`). `.env.example` shows the format for teammates.
- **Security:** every table has row-level security, and the schema isn't served by Supabase's
  public REST API, so the publishable key (the one in `index.html`) can't read password hashes or
  change anything. Only this server, which holds the secret connection string, can.

The app creates its schema and tables on first start (`schema_postgres.sql`; you can also run that
in Supabase's SQL Editor).

### Host the website on Render (free) with `render.yaml`

`render.yaml` describes the whole website for Render: build and start commands, Python version,
and environment variables.

1. Commit and push to GitHub (`.env` stays local because it's in `.gitignore`).
2. On [render.com](https://render.com), sign in with GitHub and click **New + → Blueprint**.
3. Pick the `SASE-Hackathon` repo. Render reads `render.yaml` and shows a `sooner-buddies` web service.
4. It asks for **`DATABASE_URL`**. Paste the `DATABASE_URL` value from your `.env` file
   (it starts with `postgresql://postgres.qeqrzsszxdkbcgusbtgh:`). `SECRET_KEY` is generated for you.
5. Click **Apply**. After the build (a few minutes), open the `https://sooner-buddies-....onrender.com`
   link, sign up, and the new account appears in Supabase under `sooner_buddies → users`.

Every push to GitHub redeploys automatically, and nothing is lost, because the data is in
Supabase. The free tier sleeps after 15 minutes without visitors, so the first load after that
takes about 30 seconds. Open the site a minute before you demo.

Other hosts (Railway, Fly.io, PythonAnywhere) work the same way: `pip install -r requirements.txt`,
start with `gunicorn app:app --workers 2 --threads 4 --timeout 60`, and set `DATABASE_URL` and
`SECRET_KEY` as environment variables.

### Things to know

- **Don't run `seed.py` against Supabase.** It deletes every account, so it refuses to run while
  `DATABASE_URL` is set and only ever touches a local SQLite file.
- **Raids** sync from SoonerSports.com into Supabase on their own when someone opens the Raids tab.
- **Change the database password before going public.** It has been shared in chat. In Supabase:
  **Project Settings → Database → Reset database password**, then update `.env` and the
  `DATABASE_URL` on Render.

## How it's built

Flask + SQLite locally / Supabase Postgres in production, server-rendered HTML, no build step. JavaScript is limited to the session timer,
chat polling, the map (Leaflet), and the QR scanner (jsQR). Both libraries are copied into
`static/vendor/` with their licenses; QR codes are made server-side with `segno`.

| File | Purpose |
| --- | --- |
| `app.py` | Routes and game rules: rewards, levels, parties, dungeons, raids, QR, map, clans, friends, leaderboards |
| `avatar.py` | Avatar shop items and the SVG avatar renderer |
| `pets.py` | Pet catalog, summon odds, and boosts |
| `icons.py` | Dungeon room illustrations and raid icons |
| `campus.py` | Campus outline and building coordinates for the map (from OpenStreetMap) |
| `raids.py` | Pulls events from the SoonerSports.com calendar feed (`python raids.py` syncs by hand) |
| `db.py` | Connects to Supabase Postgres when `DATABASE_URL` is set, otherwise the local SQLite file |
| `schema_postgres.sql` | The tables for Supabase (run automatically, or paste into the SQL Editor) |
| `schema.sql` | Database tables, created automatically on startup |
| `seed.py` | Demo data for presentations |
| `templates/` | Jinja HTML pages |
| `static/style.css` | OU crimson and cream theme |

Data is stored in `soonerbuddies.db` (git-ignored). The list of dungeons is `DUNGEONS` in
`app.py`, and reward rates are the constants at the top of the same file.

**Dungeon photos:** the icons are drawings. To use a real photo of a spot, save it as
`static/dungeons/<key>.jpg` (or `.png`/`.webp`), for example `static/dungeons/bizzell.jpg`. It
replaces the drawing everywhere, including the map. Use photos you have rights to.

The map loads tiles from OpenStreetMap, so it needs internet. Building positions and the campus
outline are saved in `campus.py`, so no geocoding happens at runtime.

Raids come from the JSON feed behind soonersports.com/calendar
(`/api/v2/Calendar/from/<date>/to/<date>`). The Raids page re-syncs the next 60 days when its
copy is more than 6 hours old. If the site can't be reached, it keeps showing the last synced
events. That feed is undocumented, so if SoonerSports.com changes it, `raids.py` is the only
file to update.

## Next steps

- Add non-athletics campus events from OU Engage as raids
- Rotating QR codes on a screen at each spot. Today's printed codes don't change, so a photo of one
  could be shared. Anyone signed in can also open a printable code.
- Verify study sessions (e.g. location check-in) so rewards can't be faked
- Email verification for `@ou.edu` accounts
- CSRF tokens and a real `SECRET_KEY` before deploying publicly
- Verify professor/faculty/staff roles (right now anyone can pick one, and with it the "Prof." title)
- Chat moderation (reporting, muting) and WebSockets if polling every 3 seconds gets heavy
