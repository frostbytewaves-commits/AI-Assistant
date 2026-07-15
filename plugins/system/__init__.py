"""Register built-in safe system plugins."""

from __future__ import annotations

from assistant.act.registry import ActionRegistry
from assistant.act.types import ActionResult, ActionSpec

from .launch import LAUNCH_APP_SPEC, launch_app, _APP_CATALOG
from .media import (
    MEDIA_PLAY_PAUSE_SPEC,
    VOLUME_MUTE_SPEC,
    media_play_pause,
    volume_mute,
)
from .open_url import OPEN_URL_SPEC, open_url
from .windows_ops import (
    CLOSE_WINDOW_SPEC,
    FOCUS_WINDOW_SPEC,
    close_window,
    focus_window,
)


def list_apps(_args: dict) -> ActionResult:
    ids = ", ".join(sorted(_APP_CATALOG))
    return ActionResult(
        ok=True,
        action="list_apps",
        message=f"Whitelisted apps: {ids}",
        data={"ids": sorted(_APP_CATALOG)},
    )


LIST_APPS_SPEC = ActionSpec(
    name="list_apps",
    description="List whitelist app ids that launch_app can start.",
    parameters={"type": "object", "properties": {}, "required": []},
    plugin="system",
)


def register_system_plugins(registry: ActionRegistry) -> None:
    registry.register(LAUNCH_APP_SPEC, launch_app)
    registry.register(FOCUS_WINDOW_SPEC, focus_window)
    registry.register(CLOSE_WINDOW_SPEC, close_window)
    registry.register(OPEN_URL_SPEC, open_url)
    registry.register(MEDIA_PLAY_PAUSE_SPEC, media_play_pause)
    registry.register(VOLUME_MUTE_SPEC, volume_mute)
    registry.register(LIST_APPS_SPEC, list_apps)


def action_needs_confirm(action: str, args: dict) -> bool:
    if action != "launch_app":
        return False
    app_id = str(args.get("id") or "").strip().lower()
    entry = _APP_CATALOG.get(app_id) or {}
    return bool(entry.get("needs_confirm"))
