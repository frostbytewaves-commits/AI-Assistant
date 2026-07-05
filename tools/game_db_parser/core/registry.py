"""Реестр парсеров игр."""

from __future__ import annotations

from .base import GameParser

_PARSERS: dict[str, type[GameParser]] = {}


def register_parser(cls: type[GameParser]) -> type[GameParser]:
    _PARSERS[cls.game_id] = cls
    return cls


def get_parser(game_id: str) -> GameParser | None:
    _ensure_loaded()
    parser_cls = _PARSERS.get(game_id)
    return parser_cls() if parser_cls else None


def list_parsers() -> list[GameParser]:
    _ensure_loaded()
    return [cls() for cls in _PARSERS.values()]


def _ensure_loaded() -> None:
    if _PARSERS:
        return
    from ..games.minecraft.parser import MinecraftParser  # noqa: F401
    from ..games.oni.parser import OniParser  # noqa: F401
