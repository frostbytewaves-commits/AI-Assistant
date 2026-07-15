"""Unified assistant context snapshot for the model (Sense → Context → Reason)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from ..screen_context import ScreenContext
from ..sense.window_provider import WindowInfo, WindowProvider


@dataclass
class AssistantContext:
    """Structured world snapshot — not a keyword dump."""

    window_title: str = ""
    process_name: str = ""
    active_game: str | None = None
    minecraft_window: bool = False
    oni_window: bool = False
    open_windows: list[dict[str, Any]] = field(default_factory=list)
    running_games: list[str] = field(default_factory=list)
    local_time: str = ""
    capabilities: list[str] = field(default_factory=list)
    memory_notes: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        lines = ["Host context:"]
        title = self.window_title or "(none)"
        proc = self.process_name or "(unknown)"
        lines.append(f"- Local time: {self.local_time or '(unknown)'}")
        lines.append(f"- Foreground window: {title}")
        lines.append(f"- Process: {proc}")
        if self.active_game:
            lines.append(f"- Foreground game: {self.active_game}")
        else:
            lines.append("- Foreground game: none detected")
        if self.running_games:
            lines.append(f"- Running supported games: {', '.join(self.running_games)}")
        if self.open_windows:
            lines.append("- Open top-level windows (use for 'what is open/running' — no screenshot needed):")
            for i, win in enumerate(self.open_windows[:18], start=1):
                wtitle = str(win.get("title") or "").strip() or "(untitled)"
                wproc = str(win.get("process_name") or "").strip() or "?"
                mark = " [foreground]" if win.get("is_foreground") else ""
                lines.append(f"  {i}. {wtitle} ({wproc}){mark}")
        else:
            lines.append("- Open windows: (inventory unavailable)")
        if self.capabilities:
            lines.append(f"- Capabilities: {', '.join(self.capabilities)}")
        if self.memory_notes:
            lines.append(f"- Memory: {self.memory_notes}")
        return "\n".join(lines)

    def open_windows_summary(self, *, limit: int = 10) -> str:
        if not self.open_windows:
            return ""
        parts: list[str] = []
        for win in self.open_windows[:limit]:
            title = str(win.get("title") or "").strip()
            if not title:
                continue
            parts.append(title)
        return "; ".join(parts)

    def to_screen_context(self) -> ScreenContext:
        return ScreenContext(
            foreground_title=self.window_title,
            process_name=self.process_name,
            minecraft_window=self.minecraft_window,
            oni_window=self.oni_window,
            open_windows_summary=self.open_windows_summary(),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextBuilder:
    """Assembles AssistantContext from Sense providers. Does not call the LLM."""

    def __init__(
        self,
        *,
        window_provider: WindowProvider | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        self._windows = window_provider or WindowProvider()
        self._capabilities = list(capabilities or [])

    def build(
        self,
        *,
        excluded_hwnd: int | None = None,
        screen_context: ScreenContext | None = None,
        memory_notes: str = "",
        extra_capabilities: list[str] | None = None,
        include_open_windows: bool = True,
    ) -> AssistantContext:
        window: WindowInfo = self._windows.snapshot(
            excluded_hwnd=excluded_hwnd,
            include_open=include_open_windows,
        )
        caps = list(self._capabilities)
        if extra_capabilities:
            caps.extend(extra_capabilities)

        active_game = window.active_game
        if screen_context and screen_context.active_game and not active_game:
            active_game = screen_context.active_game

        open_windows = [
            {
                "title": e.title,
                "process_name": e.process_name,
                "is_foreground": e.is_foreground,
                "game_id": e.game_id,
            }
            for e in window.open_windows
        ]

        return AssistantContext(
            window_title=window.title,
            process_name=window.process_name,
            active_game=active_game,
            minecraft_window=window.minecraft_window,
            oni_window=window.oni_window,
            open_windows=open_windows,
            running_games=list(window.running_games),
            local_time=datetime.now().strftime("%Y-%m-%d %H:%M (%A)"),
            capabilities=caps,
            memory_notes=memory_notes.strip(),
        )


# Architecture name (docs/JARVIS_ARCHITECTURE.md).
ContextManager = ContextBuilder

# Re-export for type hints in callers.
__all__ = [
    "AssistantContext",
    "ContextBuilder",
    "ContextManager",
]
