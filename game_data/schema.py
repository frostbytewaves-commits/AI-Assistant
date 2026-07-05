"""Чтение registry.json и meta.json игры."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameRegistryEntry:
    id: str
    name: str
    name_ru: str
    version_note: str = ""
    default: bool = False
    parser: str | None = None
    collections: dict[str, str] = field(default_factory=dict)


def load_registry(games_dir: Path) -> dict[str, GameRegistryEntry]:
    path = games_dir / "registry.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, GameRegistryEntry] = {}
    for gid, entry in raw.items():
        result[gid] = GameRegistryEntry(
            id=gid,
            name=entry.get("name", gid),
            name_ru=entry.get("name_ru", gid),
            version_note=entry.get("version_note", ""),
            default=bool(entry.get("default")),
            parser=entry.get("parser"),
            collections=dict(entry.get("collections") or {}),
        )
    return result


def load_game_meta(game_dir: Path) -> dict:
    path = game_dir / "meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collection_path(game_dir: Path, registry_entry: GameRegistryEntry, collection: str) -> Path:
    filename = registry_entry.collections.get(collection, f"{collection}.json")
    return game_dir / filename
