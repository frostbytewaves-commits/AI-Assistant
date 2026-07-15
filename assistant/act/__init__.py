"""Act layer: registry, executor, planner helpers."""

from __future__ import annotations

import sys

from .executor import ToolExecutor
from .planner import parse_action_plan
from .registry import ActionRegistry, CapabilityRegistry
from .types import ActionRequest, ActionResult, ActionSpec


def build_default_registry() -> ActionRegistry:
    from ..config import BASE_DIR

    root = str(BASE_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    from plugins.system import register_system_plugins

    registry = ActionRegistry()
    register_system_plugins(registry)
    return registry


__all__ = [
    "ActionRegistry",
    "CapabilityRegistry",
    "ActionRequest",
    "ActionResult",
    "ActionSpec",
    "ToolExecutor",
    "parse_action_plan",
    "build_default_registry",
]
