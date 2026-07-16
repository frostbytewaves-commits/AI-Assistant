"""MemoryBackend + MemoryManager unit tests."""

from __future__ import annotations

from pathlib import Path

from assistant.memory import (
    InMemoryBackend,
    JsonMemoryBackend,
    MemoryManager,
)


def test_json_backend_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    backend = JsonMemoryBackend(path)
    backend.save({"user_preferences": {"answer_style": "brief_first"}, "corrections": ["x"]})
    loaded = backend.load()
    assert loaded["corrections"] == ["x"]
    assert path.exists()


def test_json_backend_missing_file(tmp_path: Path) -> None:
    backend = JsonMemoryBackend(tmp_path / "nope.json")
    assert backend.load() == {}


def test_manager_load_merges_defaults(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    JsonMemoryBackend(path).save({"corrections": ["remember dark mode"]})
    mem = MemoryManager.load(path)
    assert mem.data["corrections"] == ["remember dark mode"]
    assert "minecraft" in mem.data["games"]
    assert mem.data["user_preferences"]["assume_vanilla"] is True


def test_in_memory_backend_swap() -> None:
    """Same facade works with a non-JSON backend — the point of MemoryBackend."""
    backend = InMemoryBackend()
    mem = MemoryManager.load(Path("unused.json"), backend=backend)
    mem.update_from_user("remember I prefer short answers")
    assert any("short answers" in c.lower() or "remember" in c.lower() for c in mem.data["corrections"])
    reloaded = MemoryManager.load(Path("unused.json"), backend=backend)
    assert reloaded.data["corrections"]


def test_vanilla_confirmation_updates_game() -> None:
    backend = InMemoryBackend()
    mem = MemoryManager.load(Path("x"), backend=backend)
    mem.update_from_user("I play minecraft vanilla")
    mc = mem.data["games"]["minecraft"]
    assert mc["vanilla_confirmed"] is True
    assert mc["mods_confirmed"] is False


def test_format_context_mentions_general_assistant() -> None:
    backend = InMemoryBackend()
    mem = MemoryManager.load(Path("x"), backend=backend)
    text = mem.format_context()
    assert "general desktop assistant" in text
    assert "minecraft" in text
