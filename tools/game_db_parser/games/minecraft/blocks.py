"""Все блоки + added_in / removed_in по версиям."""

from __future__ import annotations

from .data_api import block_display_name, load_blocks, load_language, versions_for_tracking
from game_data.minecraft_versions import default_version_order as _ordered_versions


def build_blocks_db(
    *,
    data_versions: list[str] | None = None,
    max_version: str | None = None,
    wiki_supplements: dict[str, list[dict]] | None = None,
) -> tuple[dict[str, dict], dict[str, dict]]:
    data_versions = data_versions or versions_for_tracking(max_version)
    order_index = {v: i for i, v in enumerate(_ordered_versions())}
    sorted_data = sorted(data_versions, key=lambda v: order_index.get(v, 999))

    blocks: dict[str, dict] = {}
    snapshots: dict[str, set[str]] = {}

    for ver in sorted_data:
        try:
            raw = load_blocks(ver)
            lang = load_language(ver)
        except Exception:
            continue
        names: set[str] = set()
        for b in raw:
            name = b["name"]
            if name == "air":
                continue
            names.add(name)
            if name not in blocks:
                blocks[name] = {
                    "display_name": block_display_name(b, lang),
                    "hardness": b.get("hardness"),
                    "stack_size": b.get("stackSize"),
                }
        snapshots[ver] = names

    changes: dict[str, dict] = {}
    if sorted_data:
        first = sorted_data[0]
        for name in snapshots.get(first, set()):
            blocks[name].setdefault("added_in", first)

    for i in range(1, len(sorted_data)):
        prev, curr = sorted_data[i - 1], sorted_data[i]
        prev_set = snapshots.get(prev, set())
        curr_set = snapshots.get(curr, set())
        added = sorted(curr_set - prev_set)
        removed = sorted(prev_set - curr_set)
        if added or removed:
            changes[curr] = {}
            if added:
                changes[curr]["added_blocks"] = added
            if removed:
                changes[curr]["removed_blocks"] = removed
        for name in added:
            blocks.setdefault(name, {"display_name": name.replace("_", " ").title()})
            blocks[name]["added_in"] = curr
        for name in removed:
            if name in blocks:
                blocks[name]["removed_in"] = curr

    if wiki_supplements:
        for ver, entries in wiki_supplements.items():
            added_blocks: list[str] = []
            for entry in entries:
                if entry.get("kind") != "block":
                    continue
                name = entry["id"]
                added_blocks.append(name)
                blocks[name] = {
                    "display_name": entry.get("display_name", name.replace("_", " ").title()),
                    "added_in": ver,
                    "wiki_source": True,
                }
                if entry.get("name_ru"):
                    blocks[name]["name_ru"] = entry["name_ru"]
            if added_blocks:
                ch = changes.setdefault(ver, {})
                ch["added_blocks"] = sorted(set(ch.get("added_blocks", []) + added_blocks))

    return blocks, changes
