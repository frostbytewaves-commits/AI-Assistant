"""Unified assistant context snapshot for the model (Sense → Context → Reason)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    capabilities: list[str] = field(default_factory=list)
    memory_notes: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        lines = ["Host context:"]
        title = self.window_title or "(none)"
        proc = self.process_name or "(unknown)"
        lines.append(f"- Foreground window: {title}")
        lines.append(f"- Process: {proc}")
        if self.active_game:
            lines.append(f"- Active game: {self.active_game}")
        else:
            lines.append("- Active game: none detected")
        if self.capabilities:
            lines.append(f"- Capabilities: {', '.join(self.capabilities)}")
        if self.memory_notes:
            lines.append(f"- Memory: {self.memory_notes}")
        return "\n".join(lines)

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
    ) -> AssistantContext:
        window: WindowInfo = self._windows.snapshot(excluded_hwnd=excluded_hwnd)
        caps = list(self._capabilities)
        if extra_capabilities:
            caps.extend(extra_capabilities)

        active_game = window.active_game
        if screen_context and screen_context.active_game and not active_game:
            active_game = screen_context.active_game

        return AssistantContext(
            window_title=window.title,
            process_name=window.process_name,
            active_game=active_game,
            minecraft_window=window.minecraft_window,
            oni_window=window.oni_window,
            capabilities=caps,
            memory_notes=memory_notes.strip(),
        )
