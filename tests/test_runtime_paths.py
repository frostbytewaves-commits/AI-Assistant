"""App root / bundle paths for frozen (PyInstaller) builds."""

from __future__ import annotations

from assistant.runtime_paths import app_root, bundle_dir, is_frozen


def test_dev_paths_point_at_repo() -> None:
    assert not is_frozen()
    root = app_root()
    assert (root / "run_assistant.py").exists() or (root / "assistant").is_dir()
    assert bundle_dir() == app_root()
