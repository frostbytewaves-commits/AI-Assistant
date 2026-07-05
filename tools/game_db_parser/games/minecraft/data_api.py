"""Загрузка JSON из PrismarineJS/minecraft-data."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

MINECRAFT_DATA_BASE = (
    "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data/pc"
)
USER_AGENT = "AI-Assistant-GameDBParser/1.0"

# Версии с полным набором blocks/items/recipes (без запроса к GitHub API)
TRACKED_DATA_VERSIONS = (
    "1.21.1",
    "1.21.3",
    "1.21.4",
    "1.21.5",
    "1.21.6",
    "1.21.8",
    "1.21.9",
    "1.21.11",
)


def fetch_json(url: str, *, retries: int = 4) -> object:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    assert last_err is not None
    raise last_err


def data_url(version: str, filename: str) -> str:
    return f"{MINECRAFT_DATA_BASE}/{version}/{filename}"


def discover_data_versions() -> list[str]:
    """Список версий без сетевых запросов (GitHub API часто падает по SSL)."""
    return list(TRACKED_DATA_VERSIONS)


def versions_for_tracking(max_version: str | None = None) -> list[str]:
    from game_data.minecraft_versions import default_version_order, version_index

    order = default_version_order()
    versions = [v for v in TRACKED_DATA_VERSIONS if v in order]
    if not max_version:
        return versions
    max_idx = version_index(max_version, order)
    return [v for v in versions if version_index(v, order) <= max_idx]


def load_blocks(version: str) -> list[dict]:
    return fetch_json(data_url(version, "blocks.json"))  # type: ignore[return-value]


def load_items(version: str) -> list[dict]:
    return fetch_json(data_url(version, "items.json"))  # type: ignore[return-value]


def load_recipes(version: str) -> dict:
    return fetch_json(data_url(version, "recipes.json"))  # type: ignore[return-value]


def load_language(version: str) -> dict[str, str]:
    try:
        return fetch_json(data_url(version, "language.json"))  # type: ignore[return-value]
    except Exception:
        return {}


def block_display_name(block: dict, lang: dict[str, str]) -> str:
    key = f"block.minecraft.{block['name']}"
    return lang.get(key, block.get("displayName", block["name"]))


def item_display_name(item: dict, lang: dict[str, str]) -> str:
    key = f"item.minecraft.{item['name']}"
    return lang.get(key, item.get("displayName", item["name"]))
