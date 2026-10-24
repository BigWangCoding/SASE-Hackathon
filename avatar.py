"""Avatar items and drawing.

Every avatar is an SVG drawn on the same 120-unit-wide canvas, so each item is just a few
shapes placed where that body part sits. Prices are in Crimson Crystals (CC).
"""
import json

from markupsafe import Markup, escape

SLOTS = {
    "hair": "Hair",
    "hat": "Hats",
    "eyewear": "Eyewear",
    "shirt": "Shirts",
    "pants": "Pants",
    "shoes": "Shoes",
    "accessory": "Accessories",
}
REQUIRED_SLOTS = {"hair", "shirt", "pants", "shoes"}  # everything else can be taken off
SKIN_TONES = ["#f6d5b8", "#e8b48a", "#c98d5f", "#8d5a3b", "#5c3a26"]


def _item(name, slot, price, svg, back=""):
    """`svg` is drawn in the item's own layer; `back` is drawn behind the whole body."""
    return {"name": name, "slot": slot, "price": price, "svg": svg, "back": back}


def _sleeves(color):
    return (f'<rect x="27" y="80" width="14" height="32" rx="7" fill="{color}"/>'
            f'<rect x="79" y="80" width="14" height="32" rx="7" fill="{color}"/>')


def _torso(color, bottom=120):
    """Shirt body. A bigger `bottom` makes a longer coat or robe."""
    flare = (bottom - 120) // 6
    return f'<path d="M40 82Q40 76 47 76H73Q80 76 80 82L{81 + flare} {bottom}H{39 - flare}Z" fill="{color}"/>'


def _pants(color, length=30, extra=""):
    return (f'<rect x="40" y="114" width="40" height="12" rx="4" fill="{color}"/>'
            f'<rect x="41" y="116" width="18" height="{length}" rx="5" fill="{color}"/>'
            f'<rect x="61" y="116" width="18" height="{length}" rx="5" fill="{color}"/>{extra}')


def _shoes(color, sole, top=141):
    height = 152 - top
    return (f'<rect x="38" y="{top}" width="21" height="{height}" rx="5" fill="{color}"/>'
            f'<rect x="61" y="{top}" width="21" height="{height}" rx="5" fill="{color}"/>'
            f'<rect x="36" y="148" width="24" height="4" rx="2" fill="{sole}"/>'
            f'<rect x="60" y="148" width="24" height="4" rx="2" fill="{sole}"/>')


_CROP = "M33 48Q31 20 60 19Q89 20 87 48Q84 33 70 31Q60 37 47 32Q37 36 33 48Z"

ITEMS = {
    # Hair
    "hair_crop": _item("Classic Crop", "hair", 0, f'<path fill="#5b3a29" d="{_CROP}"/>'),
    "hair_mohawk": _item(
        "Sooner Mohawk", "hair", 120,
        '<path fill="#3b2416" opacity=".3" d="M35 44Q36 28 50 24V32Q40 34 35 44ZM85 44Q84 28 70 24V32Q80 34 85 44Z"/>'
        '<path fill="#a3243a" d="M52 36Q52 10 60 2Q68 10 68 36Q60 31 52 36Z"/>'),
    "hair_bob": _item(
        "Bob Cut", "hair", 150,
        '<path fill="#7a4a2a" d="M33 44Q32 17 60 17Q88 17 87 44Q74 35 60 36Q46 35 33 44Z"/>',
        back='<path fill="#7a4a2a" d="M30 44Q28 78 38 80H82Q92 78 90 44Q88 17 60 17Q32 17 30 44Z"/>'),
    "hair_swoop": _item(
        "Golden Swoop", "hair", 180,
        '<path fill="#e2b04a" d="M33 48Q30 16 64 16Q92 18 87 46Q80 28 60 30Q42 33 33 48Z"/>'
        '<path d="M62 17Q78 6 86 16" fill="none" stroke="#e2b04a" stroke-width="5" stroke-linecap="round"/>'),
    "hair_waves": _item(
        "Long Waves", "hair", 200,
        '<path fill="#2b1b14" d="M33 50Q30 17 60 17Q90 17 87 50Q83 31 66 29Q54 40 35 46Z'
        'M34 44Q27 70 36 94Q43 87 40 62ZM86 44Q93 70 84 94Q77 87 80 62Z"/>',
        back='<path fill="#2b1b14" d="M31 46Q28 98 42 100H78Q92 98 89 46Q88 18 60 17Q32 18 31 46Z"/>'),
    "hair_spikes": _item(
        "Crimson Spikes", "hair", 220,
        '<path fill="#a3243a" d="M33 46L35 24L43 30L46 14L54 26L60 10L66 26L74 14L77 30L85 24L87 46'
        'Q80 32 60 32Q40 32 33 46Z"/>'),
    "hair_buns": _item(
        "Space Buns", "hair", 240,
        f'<g fill="#3b2416"><circle cx="35" cy="22" r="11"/><circle cx="85" cy="22" r="11"/><path d="{_CROP}"/></g>'),
    "hair_curls": _item(
        "Big Curls", "hair", 260,
        '<g fill="#1d1410"><circle cx="38" cy="36" r="11"/><circle cx="44" cy="24" r="11"/>'
        '<circle cx="56" cy="17" r="11"/><circle cx="68" cy="17" r="11"/><circle cx="78" cy="24" r="11"/>'
        '<circle cx="83" cy="36" r="11"/><circle cx="60" cy="27" r="12"/></g>'),

    # Hats
    "hat_beanie": _item(
        "Cozy Beanie", "hat", 120,
        '<path fill="#2f4f6f" d="M33 38Q33 10 60 10Q87 10 87 38Z"/>'
        '<rect x="31" y="31" width="58" height="10" rx="4" fill="#24405a"/><circle cx="60" cy="8" r="7" fill="#f2c66d"/>'),
    "hat_cap": _item(
        "Crimson Cap", "hat", 150,
        '<path fill="#841617" d="M33 40Q33 14 60 14Q87 14 87 40Z"/>'
        '<path fill="#5f1011" d="M30 40Q60 30 90 40Q92 46 86 46Q60 40 34 46Q28 46 30 40Z"/>'
        '<circle cx="60" cy="14" r="3" fill="#5f1011"/>'),
    "hat_cowboy": _item(
        "Cowboy Hat", "hat", 280,
        '<ellipse cx="60" cy="30" rx="44" ry="8" fill="#7a4d24"/>'
        '<path fill="#8b5a2b" d="M40 30Q38 4 52 6Q60 12 68 6Q82 4 80 30Z"/>'
        '<rect x="40" y="23" width="40" height="5" fill="#841617"/>'),
    "hat_grad": _item(
        "Graduation Cap", "hat", 350,
        '<path fill="#1d1d24" d="M42 26V38Q60 44 78 38V26Z"/><path fill="#2b2b35" d="M20 22L60 8L100 22L60 36Z"/>'
        '<path d="M60 22L88 28V40" fill="none" stroke="#f2c66d" stroke-width="2"/>'
        '<circle cx="88" cy="42" r="3" fill="#f2c66d"/>'),
    "hat_wizard": _item(
        "Wizard Hat", "hat", 450,
        '<path fill="#4b2a7b" d="M30 32L57 -13Q60 -16 63 -13L90 32Z"/>'
        '<ellipse cx="60" cy="32" rx="36" ry="6" fill="#3a1f62"/>'
        '<g fill="#f2c66d"><circle cx="55" cy="10" r="2.5"/><circle cx="67" cy="20" r="2"/><circle cx="60" cy="-2" r="1.6"/></g>'),
    "hat_crown": _item(
        "Golden Crown", "hat", 600,
        '<path fill="#f2c66d" stroke="#b17a32" stroke-width="1.5" d="M38 30L36 8L48 18L60 0L72 18L84 8L82 30Z"/>'
        '<circle cx="60" cy="21" r="3.5" fill="#a3243a"/>'
        '<g fill="#3a7bd5"><circle cx="46" cy="24" r="2.5"/><circle cx="74" cy="24" r="2.5"/></g>'),

    # Eyewear
    "glasses_round": _item(
        "Scholar Specs", "eyewear", 150,
        '<g fill="none" stroke="#2a1a14" stroke-width="2"><circle cx="51" cy="51" r="7"/><circle cx="69" cy="51" r="7"/>'
        '<path d="M58 51H62M44 50L35 47M76 50L85 47"/></g>'),
    "glasses_heart": _item(
        "Heart Shades", "eyewear", 180,
        '<g fill="#e0245e"><path d="M51 58L44 51Q40 46 45 44Q49 42 51 46Q53 42 57 44Q62 46 58 51Z"/>'
        '<path d="M69 58L62 51Q58 46 63 44Q67 42 69 46Q71 42 75 44Q80 46 76 51Z"/></g>'
        '<path d="M58 48H62" stroke="#e0245e" stroke-width="2"/>'),
    "glasses_aviator": _item(
        "Aviators", "eyewear", 200,
        '<g fill="#3a2a1a" opacity=".9"><path d="M42 47H58Q58 58 50 58Q42 58 42 47Z"/>'
        '<path d="M62 47H78Q78 58 70 58Q62 58 62 47Z"/></g>'
        '<path d="M40 47H80" stroke="#c9a24a" stroke-width="1.6"/>'),
    "glasses_pixel": _item(
        "Pixel Shades", "eyewear", 240,
        '<g fill="#111"><rect x="40" y="46" width="18" height="9"/><rect x="62" y="46" width="18" height="9"/>'
        '<rect x="58" y="47" width="4" height="3"/><rect x="34" y="46" width="6" height="3"/>'
        '<rect x="80" y="46" width="6" height="3"/></g>'
        '<g fill="#fff"><rect x="43" y="48" width="4" height="3"/><rect x="65" y="48" width="4" height="3"/></g>'),
    "glasses_monocle": _item(
        "Gold Monocle", "eyewear", 320,
        '<circle cx="69" cy="51" r="7.5" fill="#fff" fill-opacity=".15" stroke="#f2c66d" stroke-width="2.2"/>'
        '<path d="M76 54Q80 70 72 80" fill="none" stroke="#f2c66d" stroke-width="1.2"/>'),

    # Shirts
    "shirt_tee": _item(
        "Basic Tee", "shirt", 0,
        _sleeves("#9aa3ad") + _torso("#9aa3ad")
        + '<path d="M52 76Q60 84 68 76" fill="none" stroke="#7b848e" stroke-width="2"/>'),
    "shirt_flannel": _item(
        "Plaid Flannel", "shirt", 150,
        _sleeves("#b33a3a") + _torso("#b33a3a")
        + '<path d="M48 76V120M60 76V120M72 76V120M40 92H80M40 106H80M27 96H41M79 96H93"'
          ' stroke="#6e1d1d" stroke-width="2.5" opacity=".6"/>'),
    "shirt_labcoat": _item(
        "Lab Coat", "shirt", 180,
        _sleeves("#f4f4f2") + _torso("#f4f4f2", bottom=136)
        + '<path d="M53 76L60 92L67 76M60 92V136" fill="none" stroke="#c9c9c3" stroke-width="2"/>'
          '<rect x="66" y="96" width="9" height="8" fill="none" stroke="#c9c9c3"/>'
          '<rect x="68" y="92" width="2" height="7" fill="#3a7bd5"/>'),
    "shirt_hoodie": _item(
        "Golden Hoodie", "shirt", 220,
        _sleeves("#e0a83a") + _torso("#e0a83a")
        + '<path fill="#c8922c" d="M47 104H73L76 118H44Z"/>'
          '<path d="M55 78L54 92M65 78L66 92" stroke="#fff" stroke-width="1.6"/>'),
    "shirt_jersey": _item(
        "Sooner Jersey", "shirt", 260,
        _sleeves("#841617") + _torso("#841617")
        + '<path d="M52 76L60 84L68 76" fill="none" stroke="#fff" stroke-width="2.5"/>'
          '<g fill="#fff"><rect x="27" y="100" width="14" height="4"/><rect x="79" y="100" width="14" height="4"/></g>'
          '<text x="60" y="110" text-anchor="middle" font-family="Arial,sans-serif" font-size="20"'
          ' font-weight="800" fill="#fff">1</text>'),
    "shirt_varsity": _item(
        "Varsity Jacket", "shirt", 340,
        _sleeves("#f3ead8") + _torso("#841617")
        + '<path d="M60 78V120" stroke="#f3ead8" stroke-width="1.5"/>'
          '<g fill="#f3ead8"><circle cx="64" cy="88" r="1.6"/><circle cx="64" cy="98" r="1.6"/>'
          '<circle cx="64" cy="108" r="1.6"/></g>'
          '<text x="50" y="98" text-anchor="middle" font-family="Georgia,serif" font-size="13"'
          ' font-weight="700" fill="#f2c66d">S</text>'),
    "shirt_robe": _item(
        "Scholar Robe", "shirt", 400,
        _sleeves("#1d1d24") + _torso("#1d1d24", bottom=144)
        + '<path d="M52 76L60 86L68 76M60 86V144" fill="none" stroke="#f2c66d" stroke-width="2.5"/>'),

    # Pants
    "pants_jeans": _item(
        "Blue Jeans", "pants", 0,
        _pants("#3d5a8a", extra='<path d="M50 118V144M70 118V144" stroke="#2f4870" stroke-width="1.2"/>')),
    "pants_khakis": _item("Khakis", "pants", 120, _pants("#c9b48a")),
    "pants_shorts": _item(
        "Cargo Shorts", "pants", 150,
        _pants("#6f7d4c", length=14,
               extra='<g fill="#5b673d"><rect x="43" y="122" width="7" height="5"/><rect x="70" y="122" width="7" height="5"/></g>')),
    "pants_joggers": _item(
        "Crimson Joggers", "pants", 200,
        _pants("#841617",
               extra='<g fill="#fff"><rect x="42" y="118" width="2.5" height="26"/><rect x="75.5" y="118" width="2.5" height="26"/></g>')),
    "pants_gold": _item(
        "Golden Trousers", "pants", 320,
        _pants("#d9a441", extra='<path d="M50 118V144M70 118V144" stroke="#b17a32" stroke-width="1.2"/>')),

    # Shoes
    "shoes_sneakers": _item("Basic Sneakers", "shoes", 0, _shoes("#f3f3f3", "#a9a9a9")),
    "shoes_hightops": _item("Crimson High-Tops", "shoes", 180, _shoes("#841617", "#fff", top=134)),
    "shoes_boots": _item(
        "Cowboy Boots", "shoes", 260,
        _shoes("#6b3d1f", "#3e2210", top=128)
        + '<path d="M44 134Q48 138 52 134M67 134Q71 138 75 134" fill="none" stroke="#c9a24a" stroke-width="1.2"/>'),
    "shoes_gold": _item("Golden Kicks", "shoes", 300, _shoes("#f2c66d", "#b17a32")),

    # Accessories
    "acc_scarf": _item(
        "Crimson Scarf", "accessory", 140,
        '<path fill="#a3243a" d="M46 73Q60 82 74 73L76 80Q60 90 44 80Z"/>'
        '<rect x="63" y="80" width="8" height="22" rx="2" fill="#a3243a"/>'),
    "acc_book": _item(
        "Spellbook", "accessory", 160,
        '<rect x="80" y="104" width="20" height="24" rx="2" fill="#4b2a7b"/>'
        '<rect x="82.5" y="106.5" width="15" height="19" fill="none" stroke="#f2c66d"/>'),
    "acc_pendant": _item(
        "Crystal Pendant", "accessory", 180,
        '<path d="M50 77L60 90L70 77" fill="none" stroke="#f2c66d" stroke-width="1.4"/>'
        '<path fill="#c8102e" stroke="#fff" stroke-width=".8" d="M60 86L65 92L60 100L55 92Z"/>'),
    "acc_backpack": _item(
        "Adventurer's Pack", "accessory", 200,
        '<path d="M45 78V112M75 78V112" stroke="#4a0c16" stroke-width="4"/>',
        back='<rect x="30" y="70" width="60" height="46" rx="12" fill="#6a1626"/>'),
    "acc_headphones": _item(
        "Focus Headphones", "accessory", 220,
        '<path d="M30 50Q30 12 60 12Q90 12 90 50" fill="none" stroke="#222" stroke-width="5"/>'
        '<g fill="#841617"><rect x="24" y="42" width="12" height="18" rx="5"/><rect x="84" y="42" width="12" height="18" rx="5"/></g>'),
    "acc_cape": _item(
        "Hero Cape", "accessory", 350,
        '<circle cx="60" cy="80" r="3.5" fill="#f2c66d"/>',
        back='<path fill="#841617" d="M42 78L20 150Q60 158 100 150L78 78Z"/>'),
    "acc_shield": _item(
        "Raid Shield", "accessory", 500,
        '<path fill="#c9a24a" stroke="#7a5a1a" stroke-width="2" d="M8 92L28 86L48 92L46 114Q28 132 10 114Z"/>'
        '<path d="M28 92V124M14 104H42" stroke="#841617" stroke-width="4"/>'),
}

DEFAULT_OUTFIT = {"hair": "hair_crop", "shirt": "shirt_tee", "pants": "pants_jeans", "shoes": "shoes_sneakers"}
FREE_ITEMS = {item_id for item_id, item in ITEMS.items() if item["price"] == 0}

# The body underneath the clothes. {skin} is filled in per user.
_LEGS = ('<rect x="43" y="116" width="14" height="30" rx="5" fill="{skin}"/>'
         '<rect x="63" y="116" width="14" height="30" rx="5" fill="{skin}"/>')
_NECK = '<rect x="53" y="66" width="14" height="16" rx="4" fill="{skin}"/>'
_HEAD = (
    '<circle cx="34" cy="116" r="6" fill="{skin}"/><circle cx="86" cy="116" r="6" fill="{skin}"/>'
    '<circle cx="34" cy="50" r="6" fill="{skin}"/><circle cx="86" cy="50" r="6" fill="{skin}"/>'
    '<circle cx="60" cy="48" r="26" fill="{skin}"/>'
    '<circle cx="51" cy="51" r="3" fill="#2a1a14"/><circle cx="69" cy="51" r="3" fill="#2a1a14"/>'
    '<circle cx="45" cy="59" r="3.5" fill="#e98b8b" opacity=".35"/>'
    '<circle cx="75" cy="59" r="3.5" fill="#e98b8b" opacity=".35"/>'
    '<path d="M53 61Q60 67 67 61" fill="none" stroke="#2a1a14" stroke-width="2.2" stroke-linecap="round"/>'
)


def outfit_of(user):
    """Equipped item id per slot, with the free starter items filling any empty required slot."""
    saved = json.loads(user["outfit"] or "{}")
    outfit = dict(DEFAULT_OUTFIT)
    outfit.update({slot: i for slot, i in saved.items() if i in ITEMS and ITEMS[i]["slot"] == slot})
    return outfit


def render(user, size=120, try_on=None, bust=False):
    """Inline SVG of a user's avatar. `try_on` previews an item; `bust` crops to head and shoulders."""
    outfit = outfit_of(user)
    if try_on:
        slot = ITEMS[try_on]["slot"]
        outfit[slot] = try_on
        if slot == "hair":
            outfit.pop("hat", None)  # so the hair being previewed isn't hidden under a hat
    worn = {slot: ITEMS[item_id] for slot, item_id in outfit.items()}
    skin = user["skin"]

    layers = [item["back"] for item in worn.values()]
    layers += [_LEGS.format(skin=skin), worn["pants"]["svg"], worn["shoes"]["svg"]]
    layers += [_NECK.format(skin=skin), worn["shirt"]["svg"], _HEAD.format(skin=skin)]
    layers += [worn[slot]["svg"] for slot in ("hair", "eyewear", "hat", "accessory") if slot in worn]

    view, height = ("12 -14 96 96", size) if bust else ("0 -16 120 172", round(size * 172 / 120))
    return Markup(
        f'<svg class="avatar{" bust" if bust else ""}" viewBox="{view}" width="{size}" height="{height}"'
        f' role="img" aria-label="{escape(user["name"])}">{"".join(layers)}</svg>'
    )
