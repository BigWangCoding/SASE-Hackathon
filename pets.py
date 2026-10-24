"""Pet summons: a gacha of Oklahoma animals. The active pet boosts CC or XP from dungeon runs and raids."""
import random

SUMMON_COST = 100        # CC per summon
DUPLICATE_REFUND = 25    # CC back when you summon a pet you already have
PITY = 50                # a Legendary is guaranteed by this many summons in a row without one

# rarity: (chance in percent, boost in percent)
RARITIES = {
    "Common": (60, 3),
    "Rare": (28, 6),
    "Epic": (10, 10),
    "Legendary": (2, 20),
}


def _pet(name, emoji, rarity, boosts, about):
    return {"name": name, "emoji": emoji, "rarity": rarity, "boosts": boosts,
            "percent": RARITIES[rarity][1], "about": about}


PETS = {
    # Common
    "bullfrog": _pet("Bullfrog", "🐸", "Common", "xp", "Oklahoma's state amphibian."),
    "raccoon": _pet("Raccoon", "🦝", "Common", "cc", "Oklahoma's state furbearer."),
    "cottontail": _pet("Cottontail", "🐇", "Common", "xp", "Lives in every county in the state."),
    "box_turtle": _pet("Box Turtle", "🐢", "Common", "cc", "The three-toed box turtle, a regular on campus paths."),
    "skunk": _pet("Striped Skunk", "🦨", "Common", "xp", "Best admired from a distance."),
    # Rare
    "collared_lizard": _pet("Collared Lizard", "🦎", "Rare", "xp", "Oklahoma's state reptile, a.k.a. the mountain boomer."),
    "honeybee": _pet("Honeybee", "🐝", "Rare", "cc", "Oklahoma's state insect."),
    "swallowtail": _pet("Black Swallowtail", "🦋", "Rare", "xp", "Oklahoma's state butterfly."),
    "wild_turkey": _pet("Wild Turkey", "🦃", "Rare", "cc", "Oklahoma's state game bird."),
    "white_bass": _pet("White Bass", "🐟", "Rare", "xp", "Oklahoma's state fish."),
    # Epic
    "bison": _pet("American Bison", "🦬", "Epic", "cc", "Oklahoma's state animal."),
    "flycatcher": _pet("Scissor-tailed Flycatcher", "🐦", "Epic", "xp", "Oklahoma's state bird."),
    "bald_eagle": _pet("Bald Eagle", "🦅", "Epic", "cc", "Spends the winter along Oklahoma's lakes."),
    # Legendary: the white ponies that pull the Sooner Schooner
    "boomer": _pet("Boomer", "🐎", "Legendary", "cc", "One of the two ponies that pull the Sooner Schooner."),
    "sooner": _pet("Sooner", "🐎", "Legendary", "xp", "The other Sooner Schooner pony. Boomer's partner."),
}


def summon(pity, rng=random):
    """One roll. Returns (pet_id, new pity counter)."""
    if pity + 1 >= PITY:
        rarity = "Legendary"
    else:
        rarity = rng.choices(list(RARITIES), weights=[chance for chance, _ in RARITIES.values()])[0]
    pet_id = rng.choice([pid for pid, pet in PETS.items() if pet["rarity"] == rarity])
    return pet_id, 0 if rarity == "Legendary" else pity + 1


def boosts(pet_id):
    """(CC boost %, XP boost %) from the active pet."""
    pet = PETS.get(pet_id)
    if pet is None:
        return 0, 0
    return (pet["percent"], 0) if pet["boosts"] == "cc" else (0, pet["percent"])
