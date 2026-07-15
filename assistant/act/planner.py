"""Parse a model tool plan into ActionRequest(s)."""

from __future__ import annotations

import json
import re
from typing import Any

from .types import ActionRequest

_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def parse_action_plan(raw: str) -> list[ActionRequest]:
    """Accept {action, args}, {steps:[...]}, or action=none."""
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = _JSON_OBJECT.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    try:
        outer_conf = float(data.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        outer_conf = 0.0

    steps = data.get("steps")
    if isinstance(steps, list) and steps:
        out: list[ActionRequest] = []
        for step in steps[:5]:
            if not isinstance(step, dict):
                continue
            req = _step_to_request(step)
            if req.confidence <= 0 and outer_conf > 0:
                req.confidence = outer_conf
            if req.action and req.action.lower() not in {"none", "null", "chat", "answer"}:
                out.append(req)
        return out

    action = str(data.get("action") or "").strip().lower()
    if action in {"", "none", "null"}:
        return []
    req = _step_to_request(data)
    if req.confidence <= 0 and outer_conf > 0:
        req.confidence = outer_conf
    return [req]


def _step_to_request(data: dict[str, Any]) -> ActionRequest:
    action = str(data.get("action") or data.get("type") or "").strip()
    if action == "tool":
        action = str(data.get("name") or data.get("tool") or "").strip()
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    if not args and isinstance(data.get("parameters"), dict):
        args = data["parameters"]
    conf = data.get("confidence", 0.0)
    try:
        confidence = float(conf)
    except (TypeError, ValueError):
        confidence = 0.0
    return ActionRequest(
        action=action,
        args=dict(args),
        confidence=confidence,
        needs_confirm=bool(data.get("needs_confirm", False)),
    )
