"""Window Sense provider — foreground + open top-level windows (no LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..capture import (
    get_foreground_process_name,
    get_foreground_window_title,
    is_minecraft_window_title,
    is_oni_window_title,
    list_visible_windows,
)

# Process → supported game id (used with title heuristics).
_GAME_PROCESSES: dict[str, str] = {
    "oxygennotincluded.exe": "oni",
    "minecraft.exe": "minecraft",
    "minecraftbedrock.exe": "minecraft",
    "minecraft.windows.exe": "minecraft",
}


@dataclass(frozen=True)
class WindowEntry:
    title: str = ""
    process_name: str = ""
    is_foreground: bool = False

    @property
    def game_id(self) -> str | None:
        return detect_game_id(self.title, self.process_name)


def detect_game_id(title: str, process_name: str = "") -> str | None:
    if is_oni_window_title(title):
        return "oni"
    if is_minecraft_window_title(title):
        return "minecraft"
    proc = (process_name or "").lower()
    return _GAME_PROCESSES.get(proc)


@dataclass(frozen=True)
class WindowInfo:
    title: str = ""
    process_name: str = ""
    minecraft_window: bool = False
    oni_window: bool = False
    open_windows: tuple[WindowEntry, ...] = field(default_factory=tuple)

    @property
    def active_game(self) -> str | None:
        if self.oni_window:
            return "oni"
        if self.minecraft_window:
            return "minecraft"
        return detect_game_id(self.title, self.process_name)

    @property
    def running_games(self) -> tuple[str, ...]:
        found: list[str] = []
        for entry in self.open_windows:
            gid = entry.game_id
            if gid and gid not in found:
                found.append(gid)
        fg = self.active_game
        if fg and fg not in found:
            found.insert(0, fg)
        return tuple(found)


class WindowProvider:
    """Sense provider: foreground window + visible top-level inventory."""

    def snapshot(
        self,
        excluded_hwnd: int | None = None,
        *,
        include_open: bool = True,
        open_limit: int = 18,
    ) -> WindowInfo:
        title = get_foreground_window_title(excluded_hwnd)
        process = get_foreground_process_name(excluded_hwnd)
        open_windows: list[WindowEntry] = []
        if include_open:
            raw = list_visible_windows(excluded_hwnd, limit=open_limit)
            fg_title = title.lower()
            fg_proc = process.lower()
            for item in raw:
                t = str(item.get("title") or "")
                p = str(item.get("process_name") or "")
                is_fg = bool(t) and t.lower() == fg_title and p.lower() == fg_proc
                if not is_fg and fg_title and t.lower() == fg_title and not fg_proc:
                    is_fg = True
                open_windows.append(
                    WindowEntry(title=t, process_name=p, is_foreground=is_fg)
                )
            if title and not any(e.is_foreground for e in open_windows):
                open_windows.insert(
                    0,
                    WindowEntry(title=title, process_name=process, is_foreground=True),
                )

        game = detect_game_id(title, process)
        return WindowInfo(
            title=title,
            process_name=process,
            minecraft_window=game == "minecraft" or is_minecraft_window_title(title),
            oni_window=game == "oni" or is_oni_window_title(title),
            open_windows=tuple(open_windows),
        )
