"""Where things are on OU's Norman campus, for the map.

Coordinates and the campus outline come from OpenStreetMap (© OpenStreetMap contributors, ODbL),
looked up once and saved here so the app makes no geocoding calls.
"""

CENTER = (35.2048, -97.4440)

# University of Oklahoma campus boundary (OSM "amenity=university" polygon), as (lat, lng).
OUTLINE = [
    (35.18954, -97.45392), (35.18914, -97.44977), (35.18526, -97.44979), (35.18529, -97.44125),
    (35.1807, -97.44124), (35.17959, -97.43646), (35.17948, -97.43219), (35.18722, -97.43226),
    (35.18722, -97.43111), (35.18919, -97.43113), (35.1892, -97.43226), (35.19121, -97.4323),
    (35.19127, -97.44147), (35.20073, -97.44134), (35.20073, -97.44022), (35.20397, -97.44021),
    (35.20397, -97.4369), (35.20746, -97.43694), (35.20745, -97.44013), (35.20874, -97.44016),
    (35.20876, -97.43893), (35.21105, -97.43892), (35.21107, -97.44515), (35.21179, -97.44515),
    (35.21203, -97.4465), (35.2124, -97.44573), (35.21294, -97.44726), (35.21106, -97.44682),
    (35.21107, -97.44896), (35.20755, -97.44898), (35.20756, -97.45085), (35.2065, -97.45086),
    (35.20649, -97.4501), (35.20574, -97.4501), (35.20573, -97.44788), (35.20398, -97.44789),
    (35.20396, -97.44717), (35.20081, -97.44707), (35.20082, -97.44798), (35.20204, -97.44798),
    (35.20205, -97.45012), (35.19226, -97.45003), (35.19226, -97.45127), (35.19035, -97.45149),
    (35.19024, -97.45392), (35.18954, -97.45392),
]

# Dungeon rooms (keys match DUNGEONS in app.py). "other" has no fixed spot.
DUNGEON_SPOTS = {
    "bizzell": (35.20804, -97.44589),
    "union": (35.20932, -97.44419),
    "gallogly": (35.21012, -97.44227),
    "devon": (35.21076, -97.44180),
    "psc": (35.20932, -97.44727),
    "rawl": (35.21029, -97.44168),
    "price": (35.20790, -97.44371),
    "sarkeys": (35.21040, -97.44038),
    "dale": (35.20428, -97.44664),
    "dorms": (35.20310, -97.44096),  # Headington Hall
}

# Athletics venues. `match` is how the venue appears in SoonerSports.com event data.
VENUES = {
    "stadium": {"name": "Gaylord Family-Oklahoma Memorial Stadium", "match": "Gaylord", "spot": (35.20568, -97.44226)},
    "lnc": {"name": "Lloyd Noble Center", "match": "Lloyd Noble", "spot": (35.18702, -97.44431)},
    "mccasland": {"name": "McCasland Field House", "match": "McCasland", "spot": (35.20797, -97.44232)},
    "kimrey": {"name": "Kimrey Family Stadium", "match": "Kimrey", "spot": (35.19095, -97.44597)},
    "loves": {"name": "Love's Field", "match": "Love's Field", "spot": (35.19100, -97.44237)},
    "crain": {"name": "John Crain Field", "match": "John Crain", "spot": (35.18853, -97.44875)},
}


def venue_for(venue_text):
    """Key of the campus venue named in an event's venue text, or None (away games, unknown venues)."""
    for key, venue in VENUES.items():
        if venue["match"].lower() in (venue_text or "").lower():
            return key
    return None
