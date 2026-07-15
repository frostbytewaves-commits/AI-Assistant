"""Open http(s) URLs in the default browser — no other schemes."""

from __future__ import annotations

import webbrowser
from typing import Any
from urllib.parse import urlparse

from assistant.act.types import ActionResult, ActionSpec


def open_url(args: dict[str, Any]) -> ActionResult:
    url = str(args.get("url") or "").strip()
    if not url:
        return ActionResult(ok=False, action="open_url", message="Missing url.")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ActionResult(
            ok=False,
            action="open_url",
            message="Only http/https URLs are allowed.",
        )
    if not parsed.netloc:
        return ActionResult(ok=False, action="open_url", message="URL host is empty.")
    try:
        webbrowser.open(url)
    except Exception as exc:
        return ActionResult(ok=False, action="open_url", message=str(exc))
    return ActionResult(ok=True, action="open_url", message=f"Opened {url}", data={"url": url})


OPEN_URL_SPEC = ActionSpec(
    name="open_url",
    description="Open an http/https URL in the default browser.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL or domain"},
        },
        "required": ["url"],
    },
    plugin="system",
)
