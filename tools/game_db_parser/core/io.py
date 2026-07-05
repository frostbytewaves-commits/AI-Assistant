"""JSON I/O для коллекций базы."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge_preserve_manual(
    fetched: dict[str, Any],
    existing: dict[str, Any] | None,
    *,
    preserve_keys: tuple[str, ...] = ("name_ru", "note"),
) -> dict[str, Any]:
    existing = existing or {}
    merged = dict(fetched)
    for key in preserve_keys:
        if existing.get(key):
            merged[key] = existing[key]
    return merged
