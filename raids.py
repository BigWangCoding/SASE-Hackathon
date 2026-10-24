"""Raids: OU athletics events pulled from the SoonerSports.com calendar.

The calendar page at soonersports.com/calendar loads its events from this JSON feed:
    /api/v2/Calendar/from/<YYYY-MM-DD>/to/<YYYY-MM-DD>
It returns one entry per day, so multi-day events (tournaments) repeat and are de-duplicated by id.

Run `python raids.py` to sync by hand. The Raids page also re-syncs on its own when the data is stale.
"""
import json
import urllib.request
from datetime import datetime, timedelta

FEED_URL = "https://soonersports.com/api/v2/Calendar/from/{start}/to/{end}"
SYNC_DAYS = 60

# Some home events come without a venue in the feed.
HOME_VENUES = {"football": "Gaylord Family-Oklahoma Memorial Stadium"}


def fetch_events(days=SYNC_DAYS, timeout=10):
    """Raw event dicts from the feed for the next `days` days, de-duplicated."""
    today = datetime.now().date()
    url = FEED_URL.format(start=today.isoformat(), end=(today + timedelta(days=days)).isoformat())
    request = urllib.request.Request(url, headers={"User-Agent": "SoonerBuddies/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        calendar_days = json.load(response)
    events = {}
    for day in calendar_days:
        for event in day.get("events") or []:
            events.setdefault(event["id"], event)
    return list(events.values())


def _clean(text):
    return " ".join((text or "").split())


def to_raid(event):
    """Feed event -> a row for the raids table."""
    sport = event.get("sport") or {}
    opponent = event.get("opponent") or {}
    media = event.get("media") or {}
    facility = event.get("facility") or {}
    home_away = event.get("locationIndicator") or "N"

    venue = _clean(facility.get("title")) or (HOME_VENUES.get(sport.get("shortname")) if home_away == "H" else "")
    city = _clean(event.get("location"))
    if home_away == "H" and (not city or city == "Norman"):
        city = "Norman, Okla."

    start = datetime.fromisoformat(event["date"])
    last_day = datetime.fromisoformat(event["enddate"]) if event.get("enddate") else start
    end = last_day.replace(hour=23, minute=59, second=59)

    if event.get("tbd"):
        time_text = "Time TBA"
    elif event.get("allDay") or not _clean(event.get("time")):
        time_text = "All day"
    else:
        time_text = _clean(event.get("time"))

    note = _clean(event.get("noplayText")) or _clean(media.get("gameNote"))
    return {
        "id": event["id"],
        "sport": _clean(sport.get("title")) or "Athletics",
        "sport_slug": sport.get("shortname") or "",
        "opponent": _clean(opponent.get("title") or event.get("eventName")) or "TBA",
        "at_vs": "at" if home_away == "A" else "vs",
        "home_away": home_away,
        "venue": venue,
        "city": city,
        "starts_at": start.isoformat(sep=" ", timespec="seconds"),
        "ends_at": end.isoformat(sep=" ", timespec="seconds"),
        "time_text": time_text,
        "tv": _clean(media.get("tv")),
        "note": note,
        "tickets_url": (event.get("ticketLink") or {}).get("url") or "",
    }


def describe(raid):
    """One or two plain sentences about the event, built from its fields."""
    def sentence(s):  # "Starkville, Miss." already ends with a period
        return s.rstrip(".") + "."

    team = f"Oklahoma {raid['sport']}"
    where = ", ".join(part for part in (raid["venue"], raid["city"]) if part)
    if raid["home_away"] == "H":
        text = sentence(f"{team} hosts {raid['opponent']}" + (f" at {where}" if where else ""))
    elif raid["home_away"] == "A":
        text = sentence(f"{team} plays at {raid['opponent']}" + (f" in {where}" if where else ""))
    else:
        text = sentence(f"{team} faces {raid['opponent']}" + (f" at {where}" if where else ""))
    if raid["note"]:
        text += " " + sentence(raid["note"])
    if raid["home_away"] == "H":
        text += " It's on campus, so bring a party and go together."
    elif raid["tv"]:
        text += f" It's on {raid['tv']}, so it makes a good watch party."
    else:
        text += " It's away from Norman, so it makes a good watch party."
    return text


def sync(db, days=SYNC_DAYS):
    """Fetch the feed and upsert it into the raids table. Returns how many events were stored."""
    rows = [to_raid(event) for event in fetch_events(days)]
    synced_at = datetime.now().isoformat(sep=" ", timespec="seconds")
    db.executemany(
        "INSERT INTO raids (id, sport, sport_slug, opponent, at_vs, home_away, venue, city, starts_at, ends_at,"
        " time_text, tv, note, tickets_url, synced_at)"
        " VALUES (:id, :sport, :sport_slug, :opponent, :at_vs, :home_away, :venue, :city, :starts_at, :ends_at,"
        " :time_text, :tv, :note, :tickets_url, :synced_at)"
        " ON CONFLICT(id) DO UPDATE SET sport = excluded.sport, sport_slug = excluded.sport_slug,"
        " opponent = excluded.opponent, at_vs = excluded.at_vs, home_away = excluded.home_away,"
        " venue = excluded.venue, city = excluded.city, starts_at = excluded.starts_at, ends_at = excluded.ends_at,"
        " time_text = excluded.time_text, tv = excluded.tv, note = excluded.note,"
        " tickets_url = excluded.tickets_url, synced_at = excluded.synced_at",
        [{**row, "synced_at": synced_at} for row in rows],
    )
    db.commit()
    return len(rows)


if __name__ == "__main__":
    from app import app, get_db

    with app.app_context():
        print(f"Synced {sync(get_db())} events from SoonerSports.com.")
