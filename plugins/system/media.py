"""OS media keys — play/pause and mute only (safe subset)."""

from __future__ import annotations

import ctypes
from typing import Any

from assistant.act.types import ActionResult, ActionSpec

user32 = ctypes.windll.user32
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD


def _tap(vk: int) -> None:
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def media_play_pause(_args: dict[str, Any]) -> ActionResult:
    try:
        _tap(VK_MEDIA_PLAY_PAUSE)
    except Exception as exc:
        return ActionResult(ok=False, action="media_play_pause", message=str(exc))
    return ActionResult(
        ok=True,
        action="media_play_pause",
        message="Sent play/pause media key.",
    )


def volume_mute(_args: dict[str, Any]) -> ActionResult:
    try:
        _tap(VK_VOLUME_MUTE)
    except Exception as exc:
        return ActionResult(ok=False, action="volume_mute", message=str(exc))
    return ActionResult(ok=True, action="volume_mute", message="Toggled mute.")


MEDIA_PLAY_PAUSE_SPEC = ActionSpec(
    name="media_play_pause",
    description="Toggle system media play/pause (Spotify, browser, etc.).",
    parameters={"type": "object", "properties": {}, "required": []},
    plugin="media",
)

VOLUME_MUTE_SPEC = ActionSpec(
    name="volume_mute",
    description="Toggle system mute.",
    parameters={"type": "object", "properties": {}, "required": []},
    plugin="media",
)
