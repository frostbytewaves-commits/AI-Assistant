"""ToolExecutor — schema check, whitelist, optional confirm gate; no NLP."""

from __future__ import annotations

import logging
import time
from typing import Any

from .registry import ActionRegistry
from .types import ActionRequest, ActionResult

log = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, registry: ActionRegistry, *, cooldown_sec: float = 8.0) -> None:
        self.registry = registry
        self.cooldown_sec = cooldown_sec
        self._last_key: str = ""
        self._last_at: float = 0.0

    def execute(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        skip_cooldown: bool = False,
    ) -> ActionResult:
        spec = self.registry.get(request.action)
        if spec is None or not spec.enabled:
            return ActionResult(
                ok=False,
                action=request.action,
                message=f"Action '{request.action}' is not in the whitelist.",
            )
        needs_confirm = bool(spec.needs_confirm or request.needs_confirm)
        if needs_confirm and not confirmed:
            return ActionResult(
                ok=False,
                action=request.action,
                message=(
                    f"Confirm to run `{request.action}` with {request.args}. "
                    "Reply yes/confirm to proceed, or no to cancel."
                ),
                needs_confirm=True,
                data={"args": dict(request.args)},
            )
        key = f"{request.action}:{sorted((request.args or {}).items())}"
        now = time.monotonic()
        if (
            not skip_cooldown
            and key == self._last_key
            and (now - self._last_at) < self.cooldown_sec
        ):
            return ActionResult(
                ok=False,
                action=request.action,
                message="Skipped duplicate tool call (cooldown).",
                data={"cooldown": True},
            )
        handler = self.registry.handler(request.action)
        if handler is None:
            return ActionResult(
                ok=False,
                action=request.action,
                message=f"No handler registered for '{request.action}'.",
            )
        try:
            args = self._coerce_args(spec.parameters, request.args)
            log.info("TOOL execute %s args=%s", request.action, args)
            result = handler(args)
            self._last_key = key
            self._last_at = now
            log.info("TOOL result %s ok=%s %s", request.action, result.ok, result.message)
            return result
        except Exception as exc:
            log.exception("TOOL failed %s", request.action)
            return ActionResult(
                ok=False,
                action=request.action,
                message=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _coerce_args(schema: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        props = schema.get("properties") or {}
        required = list(schema.get("required") or [])
        out: dict[str, Any] = {}
        for key, meta in props.items():
            if key in args and args[key] is not None:
                out[key] = args[key]
            elif "default" in meta:
                out[key] = meta["default"]
        missing = [k for k in required if k not in out]
        if missing:
            raise ValueError(f"Missing required args: {', '.join(missing)}")
        return out
