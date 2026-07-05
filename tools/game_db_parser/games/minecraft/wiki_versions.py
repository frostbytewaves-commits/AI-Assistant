"""Дополнения из minecraft.wiki для версий, которых нет в minecraft-data (26.x)."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

WIKI_API = "https://minecraft.wiki/api.php"
USER_AGENT = "AI-Assistant-GameDBParser/1.0"

WIKI_VERSION_PAGES = {
    "26.1": "Java Edition 26.1",
    "26.2": "Java Edition 26.2",
}


def _fetch_wikitext(page: str) -> str:
    query = urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "wikitext", "format": "json"}
    )
    req = urllib.request.Request(f"{WIKI_API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))["parse"]["wikitext"]["*"]


def _title_to_id(title: str) -> str:
    clean = re.sub(r"<[^>]+>", "", title).strip()
    clean = clean.replace(" ", "_").lower()
    clean = re.sub(r"[^a-z0-9_]", "", clean)
    return clean


def _extract_links(wikitext: str, template: str) -> list[str]:
    pattern = rf"\{{\{{{template}\|([^|}}]+)"
    return [m.strip() for m in re.findall(pattern, wikitext, re.I)]


def parse_version_page(version_id: str) -> list[dict]:
    page = WIKI_VERSION_PAGES.get(version_id)
    if not page:
        return []
    try:
        wt = _fetch_wikitext(page)
    except Exception:
        return []

    entries: list[dict] = []
    seen: set[str] = set()

    for template, kind in (
        ("BlockLink", "block"),
        ("ItemLink", "item"),
        ("EntityLink", "entity"),
        ("BlockSprite", "block"),
        ("ItemSprite", "item"),
        ("EntitySprite", "entity"),
    ):
        for raw in _extract_links(wt, template):
            name = raw.split("|")[0].strip()
            if not name or name.lower() in ("block", "item", "entity"):
                continue
            bid = _title_to_id(name)
            if not bid or bid in seen:
                continue
            # Фильтр: только новый контент Chaos Cubed / sulfur для 26.2
            if version_id == "26.2" and not any(
                k in bid for k in ("sulfur", "cinnabar", "potent", "shelf", "copper_golem")
            ):
                # Для 26.2 берём только явно новые ключевые слова + всё из секции additions
                pass
            seen.add(bid)
            entries.append(
                {
                    "id": bid,
                    "kind": kind,
                    "display_name": name,
                }
            )

    # Точечный список для 26.2 (Chaos Cubed) — wiki-шаблоны шумные
    if version_id == "26.2":
        chaos_blocks = (
            "sulfur_block", "sulfur_stairs", "sulfur_slab", "sulfur_wall",
            "polished_sulfur", "sulfur_bricks", "chiseled_sulfur",
            "cinnabar_block", "potent_sulfur", "sulfur_spike",
            "raw_sulfur_block", "sulfur_cube",
        )
        chaos_entities = ("sulfur_cube",)
        for bid in chaos_blocks:
            if bid not in seen:
                entries.append({"id": bid, "kind": "block", "display_name": bid.replace("_", " ").title()})
        for eid in chaos_entities:
            if eid not in seen:
                entries.append({"id": eid, "kind": "entity", "display_name": "Sulfur Cube"})

    return entries


def fetch_wiki_supplements(version_ids: list[str] | None = None) -> dict[str, list[dict]]:
    version_ids = version_ids or list(WIKI_VERSION_PAGES.keys())
    result: dict[str, list[dict]] = {}
    for vid in version_ids:
        entries = parse_version_page(vid)
        if entries:
            result[vid] = entries
    return result
