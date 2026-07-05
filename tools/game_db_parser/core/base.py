"""Базовый интерфейс парсера игры."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PopulateContext:
    game_id: str
    game_dir: Path
    games_dir: Path
    collections: list[str]
    only_missing: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class PopulateResult:
    updated: dict[str, int] = field(default_factory=dict)
    processed: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class GameParser(ABC):
    game_id: str

    @abstractmethod
    def available_collections(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def populate(self, ctx: PopulateContext) -> PopulateResult:
        raise NotImplementedError

    def describe(self) -> str:
        return f"{self.game_id}: {', '.join(self.available_collections())}"
