"""Сборка versions.json и version_changes.json."""

from __future__ import annotations

from game_data.minecraft_versions import default_version_order

from .data_api import TRACKED_DATA_VERSIONS
from .wiki_versions import WIKI_VERSION_PAGES

_ordered_versions = default_version_order


def build_versions_manifest(
    *,
    default_play_version: str = "1.21.11",
    data_versions: list[str] | None = None,
) -> dict:
    data_versions = data_versions or list(TRACKED_DATA_VERSIONS)
    wiki_versions = list(WIKI_VERSION_PAGES.keys())
    order = [v for v in _ordered_versions() if v in data_versions or v in wiki_versions]

    return {
        "default_play_version": default_play_version,
        "order": order,
        "data_sources": {
            v: {"type": "minecraft-data", "id": v} for v in data_versions
        },
        "wiki_sources": {
            v: {"type": "minecraft.wiki", "page": WIKI_VERSION_PAGES[v]} for v in wiki_versions
        },
        "notes": (
            "play_version — версия, на которой вы играете. "
            "Блоки/рецепты с added_in новее вашей версии недоступны в игре."
        ),
    }
