"""Capability / action registry — plugins register here without patching the core router."""

from __future__ import annotations

from .types import ActionHandler, ActionSpec


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
        lines.extend(s.catalog_line() for s in specs)
        return "\n".join(lines)

    def names(self) -> list[str]:
        return [s.name for s in self.list_specs()]


# Architecture alias
CapabilityRegistry = ActionRegistry
