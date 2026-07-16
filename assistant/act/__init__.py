"""Act layer: registry, executor, planner helpers, plugin discovery."""

from __future__ import annotations

from .executor import ToolExecutor
from .planner import parse_action_plan
from .plugin import PluginRuntime, load_plugins
from .registry import ActionRegistry, CapabilityRegistry
from .types import ActionRequest, ActionResult, ActionSpec


def build_default_registry() -> ActionRegistry:
    """Load all plugins under plugins/ into a fresh registry."""
    return load_plugins().registry


def load_default_plugins(*, enabled: list[str] | None = None) -> PluginRuntime:
    return load_plugins(enabled=enabled)


__all__ = [
    "ActionRegistry",
    "CapabilityRegistry",
    "ActionRequest",
    "ActionResult",
    "ActionSpec",
    "PluginRuntime",
    "ToolExecutor",
    "parse_action_plan",
    "build_default_registry",
    "load_default_plugins",
    "load_plugins",
]
