"""Window Sense provider — foreground title / process / game hints."""

from __future__ import annotations

from dataclasses import dataclass

from ..capture import (
    get_foreground_process_name,
    get_foreground_window_title,
    is_minecraft_window_title,
    is_oni_window_title,
)


@dataclass(frozen=True)
class WindowInfo:
    title: str = ""
    process_name: str = ""
    minecraft_window: bool = False
    oni_window: bool = False

    @property
    def active_game(self) -> str | None:
        if self.oni_window:
            return "oni"
        if self.minecraft_window:
            return "minecraft"
        return None


class WindowProvider:
    """Sense provider: current foreground window (no LLM)."""

    def snapshot(self, excluded_hwnd: int | None = None) -> WindowInfo:
        title = get_foreground_window_title(excluded_hwnd)
        process = get_foreground_process_name(excluded_hwnd)
        return WindowInfo(
            title=title,
            process_name=process,
            minecraft_window=is_minecraft_window_title(title),
            oni_window=is_oni_window_title(title),
        )
