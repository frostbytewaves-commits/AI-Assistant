"""In-memory MemoryBackend for tests (no disk)."""

from __future__ import annotations

from typing import Any

from assistant.memory.backend import MemoryBackend


class InMemoryBackend(MemoryBackend):
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data = dict(initial or {})

    def load(self) -> dict[str, Any]:
        return dict(self._data)

    def save(self, data: dict[str, Any]) -> None:
        self._data = dict(data)
