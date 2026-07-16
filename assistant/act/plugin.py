"""Plugin discovery — packages under plugins/ register without editing core."""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .registry import ActionRegistry
from .types import ActionRequest

log = logging.getLogger(__name__)

NormalizeFn = Callable[[ActionRequest], ActionRequest]
ConfirmFn = Callable[[str, dict], bool]
HostHintFn = Callable[[], str]
NotesFn = Callable[[], str]


class Plugin(Protocol):
    """Minimal plugin contract: one register() entrypoint."""

    def register(self, registry: ActionRegistry) -> None: ...


@dataclass
class PluginRuntime:
    """Loaded plugins + optional hooks collected from each package."""

    registry: ActionRegistry
    loaded: list[str] = field(default_factory=list)
    _normalize: list[NormalizeFn] = field(default_factory=list)
    _confirm: list[ConfirmFn] = field(default_factory=list)
    _host_hints: list[HostHintFn] = field(default_factory=list)
    _planner_notes: list[str] = field(default_factory=list)

    def normalize(self, request: ActionRequest) -> ActionRequest:
        req = request
        for fn in self._normalize:
            try:
                req = fn(req)
            except Exception:
                log.exception("plugin normalize failed")
        return req

    def needs_confirm(self, action: str, args: dict) -> bool:
        for fn in self._confirm:
            try:
                if fn(action, args or {}):
                    return True
            except Exception:
                log.exception("plugin needs_confirm failed")
        return False

    def host_hint(self) -> str:
        parts: list[str] = []
        for fn in self._host_hints:
            try:
                text = (fn() or "").strip()
                if text:
                    parts.append(text)
            except Exception:
                log.exception("plugin host_hint failed")
        return "\n".join(parts) if parts else "(open window list unavailable)"

    def planner_notes(self) -> str:
        return "\n".join(n for n in self._planner_notes if n.strip())


def _ensure_repo_on_path(base_dir: Path) -> None:
    from ..runtime_paths import bundle_dir

    for root in (base_dir, bundle_dir()):
        s = str(root)
        if s not in sys.path:
            sys.path.insert(0, s)


def _iter_plugin_names(enabled: Sequence[str] | None) -> list[str]:
    import plugins as plugins_pkg

    found = [
        info.name
        for info in pkgutil.iter_modules(plugins_pkg.__path__)
        if info.ispkg and not info.name.startswith("_")
    ]
    found.sort()
    if enabled is None:
        return found
    allow = {n.strip().lower() for n in enabled if n and str(n).strip()}
    return [n for n in found if n.lower() in allow]


def load_plugins(
    *,
    base_dir: Path | None = None,
    enabled: Sequence[str] | None = None,
    registry: ActionRegistry | None = None,
) -> PluginRuntime:
    """Import plugins.<name> and call register(registry) on each.

    Optional package exports (any may be omitted):
      - register(registry)            required
      - PLUGIN_NAME: str
      - normalize_request(req)
      - action_needs_confirm(action, args)
      - host_hint() -> str
      - planner_notes() -> str
    """
    from ..config import BASE_DIR

    root = base_dir or BASE_DIR
    _ensure_repo_on_path(root)

    runtime = PluginRuntime(registry=registry or ActionRegistry())
    for name in _iter_plugin_names(enabled):
        mod_name = f"plugins.{name}"
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            log.exception("Failed to import plugin %s", mod_name)
            continue
        register = getattr(mod, "register", None)
        if not callable(register):
            # Backward-compatible alias used by system plugin
            register = getattr(mod, "register_system_plugins", None)
        if not callable(register):
            log.warning("Plugin %s has no register() — skipped", mod_name)
            continue
        try:
            register(runtime.registry)
        except Exception:
            log.exception("Plugin %s register() failed", mod_name)
            continue

        plugin_id = str(getattr(mod, "PLUGIN_NAME", name) or name)
        runtime.loaded.append(plugin_id)

        normalize = getattr(mod, "normalize_request", None)
        if callable(normalize):
            runtime._normalize.append(normalize)

        confirm = getattr(mod, "action_needs_confirm", None)
        if callable(confirm):
            runtime._confirm.append(confirm)

        hint = getattr(mod, "host_hint", None)
        if callable(hint):
            runtime._host_hints.append(hint)

        notes = getattr(mod, "planner_notes", None)
        if callable(notes):
            try:
                text = notes()
                if text:
                    runtime._planner_notes.append(str(text).strip())
            except Exception:
                log.exception("Plugin %s planner_notes() failed", mod_name)

        log.info("Plugin loaded: %s (%s actions so far)", plugin_id, len(runtime.registry.names()))

    return runtime
