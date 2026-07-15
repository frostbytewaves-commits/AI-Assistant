"""Whitelist app launch — ids only, no free-form shell."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from assistant.act.types import ActionResult, ActionSpec

# Safe local apps. Paths may be overridden via local_config apps whitelist later.
_APP_CATALOG: dict[str, dict[str, Any]] = {
    "notepad": {"commands": ["notepad.exe"], "label": "Notepad"},
    "calculator": {"commands": ["calc.exe"], "label": "Calculator"},
    "explorer": {"commands": ["explorer.exe"], "label": "File Explorer"},
    "settings": {"uri": "ms-settings:", "label": "Windows Settings"},
    "paint": {"commands": ["mspaint.exe"], "label": "Paint"},
    "cmd": {"commands": ["cmd.exe"], "label": "Command Prompt", "needs_confirm": True},
    "powershell": {
        "commands": ["powershell.exe", "pwsh.exe"],
        "label": "PowerShell",
        "needs_confirm": True,
    },
    "edge": {
        "commands": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "msedge.exe",
        ],
        "label": "Microsoft Edge",
    },
    "chrome": {
        "commands": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "chrome.exe",
        ],
        "label": "Google Chrome",
    },
    "vivaldi": {
        "commands": [
            r"C:\Users\{user}\AppData\Local\Vivaldi\Application\vivaldi.exe",
            "vivaldi.exe",
        ],
        "label": "Vivaldi",
    },
    "discord": {
        "commands": [
            r"C:\Users\{user}\AppData\Local\Discord\Update.exe",
            "Discord.exe",
        ],
        "args": ["--processStart", "Discord.exe"],
        "label": "Discord",
    },
    "telegram": {
        "commands": [
            r"C:\Users\{user}\AppData\Roaming\Telegram Desktop\Telegram.exe",
            "Telegram.exe",
        ],
        "label": "Telegram",
    },
    "steam": {
        "commands": [
            r"C:\Program Files (x86)\Steam\steam.exe",
            r"C:\Program Files\Steam\steam.exe",
            "steam.exe",
        ],
        "label": "Steam",
    },
    "spotify": {
        "commands": [
            r"C:\Users\{user}\AppData\Roaming\Spotify\Spotify.exe",
            "Spotify.exe",
        ],
        "label": "Spotify",
    },
    "cursor": {
        "commands": [
            r"C:\Users\{user}\AppData\Local\Programs\cursor\Cursor.exe",
            "Cursor.exe",
        ],
        "label": "Cursor",
    },
}


def _expand(path: str) -> str:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return path.replace("{user}", user)


def _resolve_command(entry: dict[str, Any]) -> tuple[str, list[str]] | None:
    if entry.get("uri"):
        return str(entry["uri"]), []
    for raw in entry.get("commands") or []:
        candidate = _expand(str(raw))
        if Path(candidate).is_file():
            return candidate, list(entry.get("args") or [])
        found = shutil.which(candidate)
        if found:
            return found, list(entry.get("args") or [])
    return None


def launch_app(args: dict[str, Any]) -> ActionResult:
    from .normalize import resolve_launch_id

    app_id = resolve_launch_id(str(args.get("id") or ""))
    if not app_id:
        return ActionResult(ok=False, action="launch_app", message="Missing app id.")
    entry = _APP_CATALOG.get(app_id)
    if entry is None:
        known = ", ".join(sorted(_APP_CATALOG))
        return ActionResult(
            ok=False,
            action="launch_app",
            message=f"App '{app_id}' is not whitelisted. Known ids: {known}",
        )
    resolved = _resolve_command(entry)
    if resolved is None:
        return ActionResult(
            ok=False,
            action="launch_app",
            message=f"Could not find {entry.get('label', app_id)} on this PC.",
        )
    target, extra = resolved
    try:
        if entry.get("uri"):
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(
                [target, *extra],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
    except Exception as exc:
        return ActionResult(ok=False, action="launch_app", message=str(exc))
    return ActionResult(
        ok=True,
        action="launch_app",
        message=f"Launched {entry.get('label', app_id)}.",
        data={"id": app_id, "target": target},
    )


LAUNCH_APP_SPEC = ActionSpec(
    name="launch_app",
    description=(
        "Start a whitelisted application by id "
        "(notepad, calculator, explorer, settings, paint, edge, chrome, vivaldi, "
        "discord, telegram, steam, spotify, cursor; cmd/powershell need confirm)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Whitelist app id",
            },
        },
        "required": ["id"],
    },
    plugin="system",
)
