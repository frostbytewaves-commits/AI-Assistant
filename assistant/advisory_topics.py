"""Curated follow-up options when the model skips the ---options--- block."""

from __future__ import annotations

import re

from .followup import extract_followup_options

TopicSpec = dict

TOPICS: list[TopicSpec] = [
    {
        "id": "minecraft_xp",
        "game": "minecraft",
        "keywords": ("xp", "experience", "level up", "levels", "опыт", "уровн"),
        "context": ("farm", "get", "lot", "fast", "quick", "much", "many", "grind"),
        "options": [
            ("1", "Zombified Piglin Farm", "Nether portal + kill chamber; best AFK XP in vanilla"),
            ("2", "Guardian Farm", "Ocean monument draining; very high XP orbs"),
            ("3", "Blaze / Mob Grinder", "Spawner-based grinder in Nether fortress or dungeon"),
            ("4", "Enderman Farm", "End dimension; massive XP once built (late game)"),
        ],
    },
    {
        "id": "minecraft_iron",
        "game": "minecraft",
        "keywords": ("iron", "iron farm", "желез"),
        "context": ("farm", "get", "automatic", "auto"),
        "options": [
            ("1", "Villager Iron Farm", "Classic villager + zombie + golem spawning platform"),
            ("2", "TNT Duplication + Mining", "Not a farm but fast bulk iron in 1.21+ if allowed"),
            ("3", "Iron Golem Spawner Room", "Smaller manual golem farm for early-mid game"),
        ],
    },
    {
        "id": "oni_co2",
        "game": "oni",
        "keywords": ("co2", "carbon", "dioxide", "углекисл"),
        "context": ("optim", "process", "system", "manage", "deal", "remove"),
        "options": [
            ("1", "CO2 Collection Pit", "Route CO2 to map bottom with mesh/airflow tiles"),
            ("2", "Carbon Skimmer Loop", "CO2 + water → polluted water → sieve"),
            ("3", "Slickster Ranch", "Convert CO2 to crude oil mid/late game"),
            ("4", "Ethanol + Petroleum Chain", "Power with managed CO2 output"),
        ],
    },
    {
        "id": "oni_oxygen",
        "game": "oni",
        "keywords": ("oxygen", "o2", "breath", "кислород", "дыш"),
        "context": ("produc", "get", "make", "setup", "spom", "farm"),
        "options": [
            ("1", "Electrolyzer SPOM", "Self-powered oxygen machine with hydrogen power"),
            ("2", "Rust Deoxidizer", "Low-power O2 from rust + salt"),
            ("3", "Algae Terrarium Room", "Early-game O2 with deodorizer"),
        ],
    },
]


def _score_topic(question: str, spec: TopicSpec) -> int:
    q = question.lower()
    score = 0
    for kw in spec["keywords"]:
        if kw in q:
            score += 3
    ctx = spec.get("context", ())
    if ctx and any(c in q for c in ctx):
        score += 2
    elif not ctx:
        score += 1
    return score


def lookup_advisory_options(question: str, game_id: str | None) -> list[dict]:
    best_score = 0
    best: list[dict] = []
    for spec in TOPICS:
        if game_id and spec["game"] != game_id:
            continue
        score = _score_topic(question, spec)
        if score > best_score:
            best_score = score
            best = [
                {"id": o[0], "title": o[1], "teaser": o[2]}
                for o in spec["options"]
            ]
    return best if best_score >= 3 else []


def format_options_block(options: list[dict]) -> str:
    lines = ["---options---"]
    for opt in options:
        lines.append(f"{opt['id']}|{opt['title']}|{opt.get('teaser', '')}")
    lines.append("---end---")
    return "\n".join(lines)


def ensure_advisory_options(
    text: str,
    question: str,
    game_id: str | None,
) -> tuple[str, list[dict]]:
    display, options = extract_followup_options(text)
    if options:
        return display, options
    curated = lookup_advisory_options(question, game_id)
    if curated:
        return display, curated
    return display, []
