"""Action / tool contracts — model proposes, code validates and executes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ActionSpec:
    """Declared capability for the model (JSON-schema style args)."""

    name: str
    description: str
    parameters: dict[str, Any]
    plugin: str = "core"
    needs_confirm: bool = False
    enabled: bool = True

    def catalog_line(self) -> str:
        confirm = " [confirm]" if self.needs_confirm else ""
        return f"- {self.name}{confirm}: {self.description}"


@dataclass
class ActionRequest:
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_confirm: bool = False


@dataclass
class ActionResult:
    ok: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    needs_confirm: bool = False

    def as_user_reply(self) -> str:
        if self.needs_confirm and not self.ok:
            return self.message
        prefix = "Done." if self.ok else "Could not run that."
        return f"{prefix} {self.message}".strip()


ActionHandler = Callable[[dict[str, Any]], ActionResult]
