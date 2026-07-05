"""Категории oxygennotincluded.wiki.gg для парсера."""

from __future__ import annotations

# Подкategории Category:Buildings (здания)
BUILDING_SUBCATEGORIES: tuple[str, ...] = (
    "Category:Automation Buildings",
    "Category:Background Buildings",
    "Category:Base Buildings",
    "Category:Buildings (Frosty Planet)",
    "Category:Debug Mode Buildings",
    "Category:Food Buildings",
    "Category:Furniture Buildings",
    "Category:Medicine Buildings",
    "Category:Oxygen Buildings",
    "Category:Plumbing Buildings",
    "Category:Power Buildings",
    "Category:Radiation Buildings",
    "Category:Recreation",
    "Category:Refinement Buildings",
    "Category:Rocket Buildings",
    "Category:Shipping Buildings",
    "Category:Special Buildings",
    "Category:Stationary Buildings",
    "Category:Storage Buildings",
    "Category:Transport Buildings",
    "Category:Utilities Buildings",
)

COLLECTIONS: dict[str, dict] = {
    "buildings": {
        "categories": BUILDING_SUBCATEGORIES,
        "label": "Building",
    },
    "elements": {
        "categories": ("Category:Solid", "Category:Gas", "Category:Liquid"),
        "label": "Element",
    },
    "critters": {
        "categories": ("Category:Critters", "Category:Critters (Spaced Out)"),
        "label": "Critter",
    },
    "geysers": {
        "categories": ("Category:Geysers",),
        "label": "Geyser",
    },
    "food": {
        "categories": ("Category:Food",),
        "label": "Food",
    },
    "diseases": {
        "categories": ("Category:Diseases",),
        "label": "Disease",
    },
    "biomes": {
        "categories": ("Category:Biomes",),
        "label": "Biome",
    },
    "research": {
        "categories": ("Category:Research",),
        "label": "Research",
    },
    "plants": {
        "categories": ("Category:Plants", "Category:Plants (Spaced Out)"),
        "label": "Plant",
    },
    "guides": {
        "categories": ("Category:Guides", "Category:Automation Guides"),
        "label": "Guide",
        "parse_mode": "guide",
        "skip_prefixes": ("Category:", "Version/", "User:"),
    },
    "topics": {
        "categories": (),
        "label": "Topic",
        "parse_mode": "static",
    },
}

SKIP_TITLES = frozenset({
    "Building",
    "Plant",
    "Critter",
    "Geyser",
    "Biome",
    "Research",
    "Duplicant",
    "Food (Resource)",
    "Consumables",
    "Food Quality",
    "Diseases",
    "Guide/Agriculture",
    "Plant/Plant comparison",
    "Furniture (Building)",
    "Automation (Building)",
    "Base (Building)",
    "Decor",
    "Overheating",
    "Flooding",
    "Piping",
    "Power",
    "Operation",
    "Cell of Interest",
    "Great Monument",
})

SKIP_PREFIXES = ("Guide/", "Category:", "Version/")
