"""Сравнение версий Minecraft (1.21.x и 26.x)."""

from __future__ import annotations

import re
from functools import cache


@cache
def default_version_order() -> tuple[str, ...]:
    return (
        "1.21.1",
        "1.21.3",
        "1.21.4",
        "1.21.5",
        "1.21.6",
        "1.21.8",
        "1.21.9",
        "1.21.11",
        "26.1",
        "26.2",
    )


def version_index(version: str, order: tuple[str, ...] | None = None) -> int:
    order = order or default_version_order()
    if version in order:
        return order.index(version)
    m_drop = re.match(r"^(\d+)\.(\d+)$", version)
    if m_drop:
        major, minor = int(m_drop.group(1)), int(m_drop.group(2))
        if major >= 26:
            return 1000 + major * 100 + minor
    m_old = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?$", version)
    if m_old:
        parts = [int(x) for x in m_old.groups() if x is not None]
        while len(parts) < 4:
            parts.append(0)
        return parts[0] * 10_000_000 + parts[1] * 100_000 + parts[2] * 100 + parts[3]
    return -1


def compare_versions(a: str, b: str, order: tuple[str, ...] | None = None) -> int:
    ia, ib = version_index(a, order), version_index(b, order)
    if ia == ib:
        return 0
    return 1 if ia > ib else -1


def version_gte(v: str, minimum: str, order: tuple[str, ...] | None = None) -> bool:
    return compare_versions(v, minimum, order) >= 0


def version_lt(v: str, other: str, order: tuple[str, ...] | None = None) -> bool:
    return compare_versions(v, other, order) < 0


def is_available(entry: dict, play_version: str, order: tuple[str, ...] | None = None) -> bool:
    added = entry.get("added_in")
    removed = entry.get("removed_in")
    if added and version_lt(play_version, added, order):
        return False
    if removed and version_gte(play_version, removed, order):
        return False
    return True
