"""Focus / close open windows (polite WM_CLOSE — no Force Kill)."""

from __future__ import annotations

import ctypes
import time
from typing import Any

from assistant.act.types import ActionResult, ActionSpec

from .window_match import find_window

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WM_CLOSE = 0x0010
SW_RESTORE = 9


def force_foreground(hwnd: int) -> bool:
    """Bring hwnd to foreground even if another app just stole focus (AttachThreadInput)."""
    if not hwnd:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        fg = int(user32.GetForegroundWindow() or 0)
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        cur_tid = kernel32.GetCurrentThreadId()

        attached_fg = False
        attached_tg = False
        if fg_tid and fg_tid != cur_tid:
            attached_fg = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        if target_tid and target_tid != cur_tid:
            attached_tg = bool(user32.AttachThreadInput(cur_tid, target_tid, True))

        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, SW_RESTORE)
        ok = bool(user32.SetForegroundWindow(hwnd))
        # Nudge: flash + set active
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)

        if attached_tg:
            user32.AttachThreadInput(cur_tid, target_tid, False)
        if attached_fg:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        return ok or int(user32.GetForegroundWindow() or 0) == hwnd
    except Exception:
        try:
            return bool(user32.SetForegroundWindow(hwnd))
        except Exception:
            return False


def focus_window(args: dict[str, Any]) -> ActionResult:
    query = str(args.get("query") or args.get("title") or "").strip()
    if not query:
        return ActionResult(ok=False, action="focus_window", message="Missing window query.")
    match = find_window(query)
    if match is None:
        return ActionResult(
            ok=False,
            action="focus_window",
            message=f"No open window matching '{query}'.",
        )
    hwnd = int(match["hwnd"])
    ok = force_foreground(hwnd)
    if not ok:
        # One quick retry after other apps settle
        time.sleep(0.25)
        ok = force_foreground(hwnd)
    return ActionResult(
        ok=True,
        action="focus_window",
        message=f"Focused «{match.get('title')}».",
        data={
            "hwnd": hwnd,
            "title": match.get("title"),
            "process_name": match.get("process_name"),
            "resolved_from": query,
            "foreground_ok": ok,
        },
    )


def close_window(args: dict[str, Any]) -> ActionResult:
    query = str(args.get("query") or args.get("title") or "").strip()
    if not query:
        return ActionResult(ok=False, action="close_window", message="Missing window query.")
    match = find_window(query)
    if match is None:
        return ActionResult(
            ok=False,
            action="close_window",
            message=f"No open window matching '{query}'.",
        )
    title = str(match.get("title") or "")
    proc = str(match.get("process_name") or "").lower()
    hay = f"{title} {proc}".lower()
    if proc == "explorer.exe" or any(
        b in hay for b in ("assistant", "ai-assistant", "game assistant")
    ):
        return ActionResult(
            ok=False,
            action="close_window",
            message=f"Refused to close protected window «{title}».",
        )
    hwnd = int(match["hwnd"])
    try:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    except Exception as exc:
        return ActionResult(ok=False, action="close_window", message=str(exc))
    return ActionResult(
        ok=True,
        action="close_window",
        message=f"Closed «{title}» ({match.get('process_name')}).",
        data={
            "hwnd": hwnd,
            "title": title,
            "process_name": match.get("process_name"),
            "resolved_from": query,
        },
    )


FOCUS_WINDOW_SPEC = ActionSpec(
    name="focus_window",
    description=(
        "Bring an already-open window to the foreground. "
        "query: title/process substring OR everyday label (vpn→Hiddify/Clash if open, "
        "browser→Chrome/Vivaldi/Edge, telegram, discord, …). Match against open windows."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Title/process substring or alias (vpn, telegram, …)",
            },
        },
        "required": ["query"],
    },
    plugin="windows",
)

CLOSE_WINDOW_SPEC = ActionSpec(
    name="close_window",
    description=(
        "Close an already-open window with WM_CLOSE (graceful). "
        "query same as focus_window — e.g. vpn resolves to open Hiddify/Clash. "
        "Will not close the Assistant itself."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Title/process substring or alias (vpn, hiddify, …)",
            },
        },
        "required": ["query"],
    },
    plugin="windows",
)
