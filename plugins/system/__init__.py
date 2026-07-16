"""Built-in system plugin — launch/focus/close/url/media (safe whitelist)."""

from __future__ import annotations

from assistant.act.registry import ActionRegistry
from assistant.act.types import ActionRequest, ActionResult, ActionSpec

from .launch import LAUNCH_APP_SPEC, launch_app, _APP_CATALOG
from .media import (
    MEDIA_PLAY_PAUSE_SPEC,
    VOLUME_MUTE_SPEC,
    media_play_pause,
    volume_mute,
)
from .normalize import normalize_action_request
from .open_url import OPEN_URL_SPEC, open_url
from .window_match import format_open_windows_hint
from .windows_ops import (
    CLOSE_WINDOW_SPEC,
    FOCUS_WINDOW_SPEC,
    close_window,
    focus_window,
)

PLUGIN_NAME = "system"


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


def register(registry: ActionRegistry) -> None:
    registry.register(LAUNCH_APP_SPEC, launch_app)
    registry.register(FOCUS_WINDOW_SPEC, focus_window)
    registry.register(CLOSE_WINDOW_SPEC, close_window)
    registry.register(OPEN_URL_SPEC, open_url)
    registry.register(MEDIA_PLAY_PAUSE_SPEC, media_play_pause)
    registry.register(VOLUME_MUTE_SPEC, volume_mute)
    registry.register(LIST_APPS_SPEC, list_apps)


# Backward-compatible alias
register_system_plugins = register


def normalize_request(req: ActionRequest) -> ActionRequest:
    return normalize_action_request(req)


def action_needs_confirm(action: str, args: dict) -> bool:
    if action != "launch_app":
        return False
    app_id = str(args.get("id") or "").strip().lower()
    entry = _APP_CATALOG.get(app_id) or {}
    return bool(entry.get("needs_confirm"))


def host_hint() -> str:
    return format_open_windows_hint()


def planner_notes() -> str:
    return (
        "- Prefer desktop apps over websites:\n"
        "  - open tg/telegram → launch_app id=telegram unless Telegram.exe is open "
        "(then focus_window).\n"
        "  - NEVER match a browser tab titled \"Telegram … Vivaldi/Chrome\". "
        "Ignore browser processes for tg/discord/steam/spotify.\n"
        "  - NEVER open_url t.me / telegram.org for messengers.\n"
        "- \"focus vpn and open tg\" → steps: focus_window(vpn/Hiddify), then "
        "launch_app(telegram). Runtime keeps the FIRST focus after later opens.\n"
        "- launch_app id must be a whitelist id (telegram, discord, steam, …). "
        "tg is an alias for telegram.\n"
        "- focus_window / close_window: use real open window process names "
        "(Hiddify.exe for vpn; Telegram.exe for tg).\n"
        "- close_window: do not close the Assistant.\n"
        "- open_url: only for arbitrary web pages named as a URL/site, "
        "not for installed messengers/games."
    )
