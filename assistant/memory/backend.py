"""MemoryBackend — persistence only. Domain logic lives in MemoryManager."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MemoryBackend(ABC):
    """Swap JSON / SQLite / vector stores without changing the facade."""

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Return the full memory document (may be empty dict if missing)."""

    @abstractmethod
    def save(self, data: dict[str, Any]) -> None:
        """Persist the full memory document."""
