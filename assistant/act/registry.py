"""Capability / action registry — plugins register here without patching the core router."""

from __future__ import annotations

from typing import Any

from .types import ActionHandler, ActionSpec


def _schema_summary(parameters: dict[str, Any]) -> str:
    props = parameters.get("properties") or {}
    if not props:
        return "args: {}"
    required = set(parameters.get("required") or [])
    parts: list[str] = []
    for key, meta in props.items():
        flag = "*" if key in required else ""
        typ = meta.get("type", "any")
        enum = meta.get("enum")
        if enum:
            typ = "|".join(str(x) for x in enum[:12])
            if len(enum) > 12:
                typ += "|…"
        default = meta.get("default", None)
        extra = f"={default!r}" if default is not None and key not in required else ""
        parts.append(f"{key}{flag}:{typ}{extra}")
    return "args: {" + ", ".join(parts) + "}"


class ActionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, spec: ActionSpec, handler: ActionHandler) -> None:
        if not spec.name or not spec.enabled:
            return
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def handler(self, name: str) -> ActionHandler | None:
        return self._handlers.get(name)

    def list_specs(self) -> list[ActionSpec]:
        return [s for s in self._specs.values() if s.enabled]

    def catalog_for_prompt(self) -> str:
        specs = self.list_specs()
        if not specs:
            return "No tools available."
        lines = ["Available tools (whitelist only — never invent new action names):"]
        for s in specs:
            confirm = " [confirm]" if s.needs_confirm else ""
            lines.append(f"- {s.name}{confirm} ({s.plugin}): {s.description}")
            lines.append(f"  {_schema_summary(s.parameters)}")
        return "\n".join(lines)

    def names(self) -> list[str]:
        return [s.name for s in self.list_specs()]


# Architecture alias
CapabilityRegistry = ActionRegistry
