"""Sense providers — OS/hardware observation (no language routing)."""

from .window_provider import WindowEntry, WindowInfo, WindowProvider, detect_game_id

__all__ = ["WindowEntry", "WindowInfo", "WindowProvider", "detect_game_id"]
