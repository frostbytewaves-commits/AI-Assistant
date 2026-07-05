"""Поиск по базе Oxygen Not Included — факты, гайды и стратегии."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game_db import GameKnowledgeBase

FACT_COLLECTIONS: tuple[str, ...] = (
    "buildings",
    "elements",
    "critters",
    "geysers",
    "food",
    "diseases",
    "biomes",
    "research",
    "plants",
)

COLLECTION_TITLES = {
    "buildings": "Building",
    "elements": "Element / resource",
    "critters": "Critter",
    "geysers": "Geyser / vent",
    "food": "Food",
    "diseases": "Disease / germ",
    "biomes": "Biome",
    "research": "Research",
    "plants": "Plant",
    "guides": "Wiki guide",
    "topics": "Strategy topic",
}

PRIORITY_FIELDS = (
    "description",
    "summary",
    "research",
    "power",
    "requires",
    "effects",
    "materials",
    "amounts",
    "overheat",
    "heat",
    "diet",
    "temperature",
    "output",
    "consumption",
    "source",
    "symptoms",
    "cure",
    "tags",
)

TOPIC_PHASES = ("early_game", "mid_game", "late_game", "strategies", "tips")


def _tokenize(question: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9_а-яА-ЯёЁ]+", question.lower()) if len(t) >= 3]


def _score_text(question: str, key: str, haystack: str, *, name: str = "") -> int:
    q = question.lower()
    score = 0
    key_spaced = key.replace("_", " ")
    if key_spaced in q or key in q:
        score += 10
    if name and name.lower() in q:
        score += 10
    for token in _tokenize(question):
        if token in haystack:
            score += 2
    return score


def _score_fact_entry(question: str, key: str, entry: dict) -> int:
    name = str(entry.get("name", ""))
    haystack = " ".join(
        [key.replace("_", " "), name.lower()]
        + [str(entry.get(f, "")).lower() for f in PRIORITY_FIELDS if entry.get(f)]
    )
    return _score_text(question, key, haystack, name=name)


def _format_fact_entry(collection: str, key: str, entry: dict) -> str:
    label = entry.get("name", key.replace("_", " ").title())
    kind = COLLECTION_TITLES.get(collection, collection)
    lines = [f"### {label} ({kind})"]
    if entry.get("description"):
        lines.append(f"**Description:** {entry['description']}")
    elif entry.get("summary"):
        lines.append(f"**Summary:** {entry['summary']}")
    for field in PRIORITY_FIELDS:
        if field in ("description", "summary", "tags"):
            continue
        val = entry.get(field)
        if val:
            title = field.replace("_", " ").title()
            lines.append(f"**{title}:** {val}")
    return "\n".join(lines)


def _format_topic(key: str, entry: dict) -> str:
    lines = [f"### {entry.get('name', key.replace('_', ' ').title())} (Strategy)"]
    if entry.get("summary"):
        lines.append(f"**Overview:** {entry['summary']}")
    for phase in TOPIC_PHASES:
        items = entry.get(phase)
        if not items:
            continue
        title = phase.replace("_", " ").title()
        if isinstance(items, list):
            lines.append(f"**{title}:**")
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append(f"**{title}:** {items}")
    related = entry.get("related_buildings")
    if related:
        lines.append(f"**Related buildings:** {', '.join(related)}")
    return "\n".join(lines)


def _score_topic(question: str, key: str, entry: dict) -> int:
    tags = " ".join(entry.get("tags", [])).lower()
    parts = [entry.get("summary", ""), tags]
    for phase in TOPIC_PHASES:
        val = entry.get(phase)
        if isinstance(val, list):
            parts.extend(val)
        elif val:
            parts.append(str(val))
    haystack = " ".join(str(p).lower() for p in parts) + " " + key.replace("_", " ")
    score = _score_text(question, key, haystack, name=entry.get("name", ""))
    for token in _tokenize(question):
        if token in tags:
            score += 4
    return score


def _format_guide(key: str, entry: dict) -> str:
    name = entry.get("name", key.replace("_", " ").title())
    lines = [f"### {name} (Wiki guide)"]
    if entry.get("summary"):
        lines.append(f"**Summary:** {entry['summary']}")
    if entry.get("description"):
        desc = entry["description"]
        if len(desc) > 1800:
            desc = desc[:1800] + "…"
        lines.append(desc)
    return "\n".join(lines)


def _score_guide(question: str, key: str, entry: dict) -> int:
    haystack = " ".join(
        [
            key.replace("_", " "),
            str(entry.get("name", "")).lower(),
            str(entry.get("summary", "")).lower(),
            str(entry.get("description", "")).lower()[:600],
            str(entry.get("tags", "")).lower(),
        ]
    )
    return _score_text(question, key, haystack, name=entry.get("name", ""))


def search_oni_facts(kb: GameKnowledgeBase, question: str, *, limit: int = 5) -> str:
    hits: list[tuple[int, str]] = []
    for collection in FACT_COLLECTIONS:
        data = kb._load_collection("oni", collection)
        for key, entry in data.items():
            score = _score_fact_entry(question, key, entry)
            if score <= 0:
                continue
            hits.append((score, _format_fact_entry(collection, key, entry)))
    hits.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(h[1] for h in hits[:limit])


def search_oni_topics(kb: GameKnowledgeBase, question: str, *, limit: int = 2) -> str:
    data = kb._load_collection("oni", "topics")
    hits: list[tuple[int, str]] = []
    for key, entry in data.items():
        score = _score_topic(question, key, entry)
        if score <= 0:
            continue
        hits.append((score, _format_topic(key, entry)))
    hits.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(h[1] for h in hits[:limit])


def search_oni_guides(kb: GameKnowledgeBase, question: str, *, limit: int = 2) -> str:
    data = kb._load_collection("oni", "guides")
    if not data:
        return ""
    hits: list[tuple[int, str]] = []
    for key, entry in data.items():
        score = _score_guide(question, key, entry)
        if score <= 0:
            continue
        hits.append((score, _format_guide(key, entry)))
    hits.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(h[1] for h in hits[:limit])


def search_oni(kb: GameKnowledgeBase, question: str, *, limit: int = 5) -> str:
    return search_oni_facts(kb, question, limit=limit)


def build_oni_context(kb: GameKnowledgeBase, question: str, *, advisory: bool = False) -> str:
    from .intent import is_advisory_question

    strategy = advisory or is_advisory_question(question)
    game = kb.get_game("oni")
    parts = [
        f"Game: {game.name_ru} ({game.id})",
        f"Source: local database ({game.version_note or 'ONI wiki + strategy topics'})",
        f"Question type: {'strategy / system design' if strategy else 'factual lookup'}",
    ]

    if strategy:
        topics = search_oni_topics(kb, question, limit=2)
        if topics:
            parts.append("")
            parts.append("=== Strategy topics ===")
            parts.append(topics)
        guides = search_oni_guides(kb, question, limit=2)
        if guides:
            parts.append("")
            parts.append("=== Wiki guides ===")
            parts.append(guides)
        facts = search_oni_facts(kb, question, limit=4)
        if facts:
            parts.append("")
            parts.append("=== Relevant buildings & resources ===")
            parts.append(facts)
        if not topics and not guides and not facts:
            parts.append("")
            parts.append("No exact strategy match — use general ONI knowledge carefully.")
    else:
        block = search_oni_facts(kb, question, limit=5)
        if block:
            parts.append("")
            parts.append("=== Game facts ===")
            parts.append(block)
        else:
            parts.append("")
            parts.append("No exact match in the database for this question.")

    return "\n".join(parts)
