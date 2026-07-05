"""Общие пути и схема внешней базы данных игр."""

from .paths import (
    DEFAULT_DATA_ROOT,
    ensure_data_layout,
    migrate_legacy_games,
    resolve_data_root,
    resolve_games_dir,
)

__all__ = [
    "DEFAULT_DATA_ROOT",
    "ensure_data_layout",
    "migrate_legacy_games",
    "resolve_data_root",
    "resolve_games_dir",
]
