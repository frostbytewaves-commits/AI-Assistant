"""Контекст экрана: определение активной игры по заголовку окна."""

from __future__ import annotations

from dataclasses import dataclass

from .capture import (
    get_foreground_process_name,
    get_foreground_window_title,
    is_minecraft_window_title,
    is_oni_window_title,
)


@dataclass
class ScreenContext:
    foreground_title: str = ""
    process_name: str = ""
    minecraft_window: bool = False
    oni_window: bool = False
    # Compact inventory from ContextManager — for router / short hints.
    open_windows_summary: str = ""

    @property
    def active_game(self) -> str | None:
        if self.oni_window:
            return "oni"
        if self.minecraft_window:
            return "minecraft"
        return None

    @classmethod
    def detect(cls, excluded_hwnd: int | None = None) -> ScreenContext:
        title = get_foreground_window_title(excluded_hwnd)
        return cls(
            foreground_title=title,
            process_name=get_foreground_process_name(excluded_hwnd),
            minecraft_window=is_minecraft_window_title(title),
            oni_window=is_oni_window_title(title),
        )
