"""Normalize model tool plans — prefer desktop apps over web URLs."""

from __future__ import annotations

from urllib.parse import urlparse

from assistant.act.types import ActionRequest

from .window_match import find_window

# Hosts that mean "open the desktop client", not the browser.
_DESKTOP_URL_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("t.me", "telegram.org", "telegram.me", "web.telegram.org"), "telegram"),
    (("discord.com", "discord.gg", "discordapp.com"), "discord"),
    (("open.spotify.com", "spotify.com"), "spotify"),
    (("store.steampowered.com", "steamcommunity.com"), "steam"),
)

_APP_ID_ALIASES: dict[str, str] = {
    "tg": "telegram",
    "тг": "telegram",
    "calc": "calculator",
    "calculator": "calculator",
    "files": "explorer",
    "file explorer": "explorer",
}

# If user says open/focus these, never use a browser tab — desktop app only.
_DESKTOP_APP_QUERIES = frozenset(
    {"telegram", "tg", "тг", "discord", "steam", "spotify", "cursor"}
)


def resolve_launch_id(app_id: str) -> str:
    raw = (app_id or "").strip().lower()
    return _APP_ID_ALIASES.get(raw, raw)


def _desktop_id_for_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlparse(raw).netloc or "").lower()
    except Exception:
        return None
    if host.startswith("www."):
        host = host[4:]
    for hosts, app_id in _DESKTOP_URL_MAP:
        if any(host == h or host.endswith("." + h) for h in hosts):
            return app_id
    return None


def _desktop_open_or_focus(app_id: str, *, confidence: float) -> ActionRequest:
    """Focus native process if running; otherwise launch — never a browser tab."""
    native = find_window(app_id, native_only=True)
    if native is not None:
        return ActionRequest(
            action="focus_window",
            args={"query": app_id},
            confidence=confidence,
            needs_confirm=False,
        )
    return ActionRequest(
        action="launch_app",
        args={"id": app_id},
        confidence=confidence,
        needs_confirm=False,
    )


def normalize_action_request(req: ActionRequest) -> ActionRequest:
    """Rewrite unsafe/wrong web opens into focus/launch of desktop apps."""
    action = (req.action or "").strip()
    args = dict(req.args or {})

    if action == "launch_app":
        app_id = resolve_launch_id(str(args.get("id") or ""))
        if app_id:
            args["id"] = app_id
        return ActionRequest(
            action=action,
            args=args,
            confidence=req.confidence,
            needs_confirm=req.needs_confirm,
        )

    if action == "open_url":
        app_id = _desktop_id_for_url(str(args.get("url") or ""))
        if app_id:
            return _desktop_open_or_focus(app_id, confidence=req.confidence)

    if action in {"focus_window", "close_window"}:
        query = str(args.get("query") or "").strip().lower()
        mapped = resolve_launch_id(query)
        if mapped:
            args["query"] = mapped
            query = mapped
        # "focus/open telegram" must not bind to a Vivaldi tab
        if action == "focus_window" and (
            query in _DESKTOP_APP_QUERIES or resolve_launch_id(query) in _DESKTOP_APP_QUERIES
        ):
            return _desktop_open_or_focus(query, confidence=req.confidence)
        return ActionRequest(
            action=action,
            args=args,
            confidence=req.confidence,
            needs_confirm=req.needs_confirm,
        )

    return req
