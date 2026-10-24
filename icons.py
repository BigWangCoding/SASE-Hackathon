"""Icons for dungeon rooms and raids.

Each dungeon room has a small drawing of the place. To use a real photo instead, save it as
static/dungeons/<key>.jpg (or .png / .webp), e.g. static/dungeons/bizzell.jpg; it takes over automatically.
"""
import os

from markupsafe import Markup, escape

PHOTO_DIR = os.path.join(os.path.dirname(__file__), "static", "dungeons")

CRIMSON, DARK, CREAM, STONE, BRICK, GLASS, INK, GRASS = (
    "#841617", "#5f1011", "#fdf9d8", "#d9cfb4", "#a5432f", "#9fc3d6", "#2a1c18", "#7fa36b")
_GROUND = f'<rect x="0" y="54" width="64" height="10" fill="{GRASS}"/>'


def _windows(x0, y0, cols, rows, w, h, gap_x, gap_y, fill):
    return "".join(
        f'<rect x="{x0 + c * gap_x}" y="{y0 + r * gap_y}" width="{w}" height="{h}" fill="{fill}"/>'
        for r in range(rows) for c in range(cols)
    )


DUNGEON_ART = {
    # Bizzell Memorial Library: Cherokee Gothic, central tower over long wings
    "bizzell": (
        f'<rect x="4" y="30" width="56" height="24" fill="{STONE}"/>'
        f'<rect x="23" y="14" width="18" height="40" fill="#cdbf9c"/>'
        f'<path d="M23 14 L32 5 L41 14Z" fill="{CRIMSON}"/>'
        + _windows(8, 35, 2, 1, 4, 11, 7, 0, DARK) + _windows(45, 35, 2, 1, 4, 11, 7, 0, DARK)
        + f'<path d="M29 20 h6 v9 h-6z M28 54 v-8 a4 4 0 0 1 8 0 v8z" fill="{DARK}"/>'
    ),
    # Oklahoma Memorial Union: brick building with its clock tower
    "union": (
        f'<rect x="4" y="30" width="40" height="24" fill="{BRICK}"/>'
        f'<rect x="43" y="10" width="14" height="44" fill="#93391f"/>'
        f'<path d="M43 10 L50 2 L57 10Z" fill="{CRIMSON}"/>'
        f'<circle cx="50" cy="20" r="4.5" fill="{CREAM}" stroke="{INK}" stroke-width="1"/>'
        f'<path d="M50 20 V17.2 M50 20 H52.2" stroke="{INK}" stroke-width="1"/>'
        + _windows(8, 35, 4, 2, 5, 5, 9, 9, CREAM)
    ),
    # Gallogly Hall: computer labs
    "gallogly": (
        f'<rect x="6" y="18" width="52" height="36" fill="#cbbb9f"/><rect x="6" y="18" width="52" height="6" fill="{CRIMSON}"/>'
        f'<rect x="17" y="29" width="30" height="19" rx="2" fill="{INK}"/><rect x="19" y="31" width="26" height="15" fill="{GLASS}"/>'
        f'<path d="M25 36 l-3 2.5 3 2.5 M39 36 l3 2.5 -3 2.5 M33 34.5 l-2 8" stroke="{DARK}" stroke-width="1.6" fill="none"/>'
        f'<rect x="29" y="48" width="6" height="3" fill="{INK}"/>'
    ),
    # Devon Energy Hall: glass engineering tower
    "devon": (
        f'<rect x="14" y="8" width="36" height="46" fill="{GLASS}"/><rect x="14" y="8" width="36" height="4" fill="{CRIMSON}"/>'
        f'<path d="M23 12 V54 M32 12 V54 M41 12 V54 M14 22 H50 M14 32 H50 M14 42 H50" stroke="#6f9bb3" stroke-width="1"/>'
        f'<rect x="27" y="45" width="10" height="9" fill="{DARK}"/>'
    ),
    # Physical Sciences Center: tall science tower, with a flask
    "psc": (
        f'<rect x="8" y="6" width="28" height="48" fill="#cbbfa3"/>' + _windows(12, 10, 4, 6, 3, 4, 6, 7, DARK)
        + f'<path d="M45 22 h8 M47 22 v9 l-7 15 a3 3 0 0 0 3 4 h12 a3 3 0 0 0 3 -4 l-7 -15 v-9" fill="{CREAM}" stroke="{INK}" stroke-width="1.4"/>'
        f'<path d="M42.5 42 h15 l2 4 a3 3 0 0 1 -3 4 h-13 a3 3 0 0 1 -3 -4z" fill="{CRIMSON}"/>'
    ),
    # Rawl Engineering Practice Facility: open workshop with a gear
    "rawl": (
        f'<path d="M5 54 V26 L32 13 L59 26 V54Z" fill="#cfc2a0"/>'
        f'<rect x="22" y="36" width="20" height="18" fill="{DARK}"/><path d="M22 41 H42 M22 46 H42 M22 51 H42" stroke="#7a2a20" stroke-width="1"/>'
        f'<circle cx="32" cy="25" r="6" fill="{CRIMSON}"/><circle cx="32" cy="25" r="2.4" fill="{CREAM}"/>'
        f'<path d="M32 16.5 v3 M32 30.5 v3 M23.5 25 h3 M37.5 25 h3 M26 19 l2 2 M36 29 l2 2 M38 19 l-2 2 M28 29 l-2 2" stroke="{CRIMSON}" stroke-width="2.4"/>'
    ),
    # Price Hall: business school with a columned front
    "price": (
        f'<rect x="6" y="28" width="52" height="26" fill="{BRICK}"/>'
        f'<path d="M4 28 L32 12 L60 28Z" fill="{CRIMSON}"/><rect x="8" y="27" width="48" height="4" fill="{CREAM}"/>'
        + _windows(12, 31, 5, 1, 4, 20, 10, 0, CREAM) + f'<rect x="6" y="51" width="52" height="3" fill="{CREAM}"/>'
    ),
    # Sarkeys Energy Center: the tall tower on Boyd Street
    "sarkeys": (
        f'<rect x="18" y="6" width="28" height="48" fill="#b8a98a"/>'
        f'<path d="M32 6 V1" stroke="{INK}" stroke-width="1.5"/><circle cx="32" cy="1.5" r="1.5" fill="{CRIMSON}"/>'
        + _windows(21, 10, 3, 7, 6, 3, 8, 6, GLASS) + f'<rect x="18" y="6" width="28" height="3" fill="{CRIMSON}"/>'
        f'<rect x="28" y="46" width="8" height="8" fill="{DARK}"/>'
    ),
    # Dale Hall: classrooms, with an open book
    "dale": (
        f'<rect x="4" y="26" width="56" height="28" fill="{BRICK}"/>' + _windows(8, 31, 6, 2, 5, 6, 9, 11, CREAM)
        + f'<path d="M32 14 C26 11 19 11 14 13 V24 C19 22 26 22 32 25 C38 22 45 22 50 24 V13 C45 11 38 11 32 14Z" fill="{CREAM}" stroke="{INK}" stroke-width="1.2"/>'
        f'<path d="M32 14 V25" stroke="{INK}" stroke-width="1.2"/>'
    ),
    # Residence halls: lit windows
    "dorms": (
        f'<rect x="8" y="14" width="48" height="40" fill="{BRICK}"/><rect x="8" y="14" width="48" height="4" fill="{DARK}"/>'
        + _windows(12, 21, 5, 4, 5, 5, 9, 8, "#f2c66d")
        + f'<rect x="28" y="45" width="8" height="9" fill="{DARK}"/>'
    ),
    # Anywhere else: a map pin
    "other": (
        f'<path d="M32 58 C22 44 16 36 16 26 a16 16 0 0 1 32 0 C48 36 42 44 32 58Z" fill="{CRIMSON}"/>'
        f'<circle cx="32" cy="26" r="6.5" fill="{CREAM}"/>'
    ),
}

RAID_ART = {
    "football": (
        f'<ellipse cx="32" cy="32" rx="25" ry="15" transform="rotate(-30 32 32)" fill="#7a3b1c"/>'
        f'<path d="M22 38 L42 26" stroke="{CREAM}" stroke-width="2.4"/>'
        f'<path d="M27 31 l3 4 M31 28.5 l3 4 M35 26 l3 4" stroke="{CREAM}" stroke-width="2"/>'
    ),
    "basketball": (
        f'<circle cx="32" cy="32" r="22" fill="#d9692b"/>'
        f'<path d="M10 32 H54 M32 10 V54 M17 16 C25 24 25 40 17 48 M47 16 C39 24 39 40 47 48" stroke="{INK}" stroke-width="2" fill="none"/>'
    ),
    "baseball": (
        f'<circle cx="32" cy="32" r="22" fill="#fbfaf5" stroke="#cfc7b6" stroke-width="1.5"/>'
        f'<path d="M20 15 C27 24 27 40 20 49 M44 15 C37 24 37 40 44 49" stroke="#c8102e" stroke-width="2" fill="none" stroke-dasharray="3 2.2"/>'
    ),
    "volleyball": (
        f'<circle cx="32" cy="32" r="22" fill="#fbfaf5" stroke="#cfc7b6" stroke-width="1.5"/>'
        f'<path d="M32 10 C22 22 24 34 32 40 M32 40 C40 46 50 44 54 34 M32 40 C24 46 14 46 11 38" stroke="{CRIMSON}" stroke-width="2.4" fill="none"/>'
    ),
    "trophy": (
        f'<path d="M22 12 H42 V24 a10 10 0 0 1 -20 0Z" fill="#e2b04a" stroke="#a87b22" stroke-width="1.5"/>'
        f'<path d="M22 15 h-6 a6 6 0 0 0 6 10 M42 15 h6 a6 6 0 0 1 -6 10" fill="none" stroke="#a87b22" stroke-width="2.4"/>'
        f'<rect x="29" y="33" width="6" height="9" fill="#a87b22"/><rect x="22" y="42" width="20" height="6" rx="1.5" fill="{CRIMSON}"/>'
    ),
    "event": (
        f'<path d="M20 8 V56" stroke="{INK}" stroke-width="3"/>'
        f'<path d="M21 10 H50 L43 20 L50 30 H21Z" fill="{CRIMSON}"/>'
        f'<path d="M30 14 l2 4 4.5 .5 -3.3 3 1 4.4 -4.2 -2.3 -4.2 2.3 1 -4.4 -3.3 -3 4.5 -.5z" fill="{CREAM}"/>'
    ),
}
SPORT_ART = {"football": "football", "mbball": "basketball", "wbball": "basketball", "baseball": "baseball",
             "softball": "baseball", "wvball": "volleyball", "vball": "volleyball"}


def _svg(body, size, label):
    return Markup(
        f'<svg class="spot-icon" viewBox="0 0 64 64" width="{size}" height="{size}" role="img" '
        f'aria-label="{escape(label)}">{body}</svg>'
    )


def dungeon_icon(key, name, size=48):
    """A photo of the spot if one was added to static/dungeons/, otherwise its drawing."""
    for ext in ("jpg", "png", "webp"):
        if os.path.exists(os.path.join(PHOTO_DIR, f"{key}.{ext}")):
            return Markup(
                f'<img class="spot-icon photo" src="/static/dungeons/{key}.{ext}" width="{size}" height="{size}" alt="{escape(name)}">'
            )
    art = DUNGEON_ART.get(key, DUNGEON_ART["other"])
    return _svg(art if key == "other" else _GROUND + art, size, name)


def raid_icon(sport_slug, label, size=32):
    """A ball for sports we have art for, a trophy for other sports, a flag for student-created raids."""
    art = "event" if sport_slug == "custom" else SPORT_ART.get(sport_slug, "trophy")
    return _svg(RAID_ART[art], size, label)
