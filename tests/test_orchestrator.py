"""Orchestrator wires context → plan → execute without owning UI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from assistant.core.orchestrator import Orchestrator
from assistant.intent import QueryIntent
from assistant.memory import InMemoryBackend, MemoryManager
from assistant.screen_context import ScreenContext


def test_handle_turn_text_only_calls_execute(tmp_path: Path) -> None:
    config = SimpleNamespace(always_capture_screen=False)
    llm = MagicMock()
    llm.plan_query.return_value = QueryIntent.fallback_text("hi")
    llm._resolve_game_id.return_value = None
    llm.execute_query.return_value = "hello"

    memory = MemoryManager.load(tmp_path / "m.json", backend=InMemoryBackend())
    orch = Orchestrator(config, llm, memory)  # type: ignore[arg-type]

    result = orch.handle_turn("hi", chat_history=[])

    assert result.answer == "hello"
    llm.plan_query.assert_called_once()
    llm.execute_query.assert_called_once()
    assert result.intent.pipeline == "text_only"


def test_handle_turn_captures_when_needed(tmp_path: Path) -> None:
    config = SimpleNamespace(always_capture_screen=False)
    llm = MagicMock()
    intent = QueryIntent(
        needs_screen=True,
        needs_web=False,
        pipeline="vision_answer",
        focus="scene",
    )
    llm.plan_query.return_value = intent
    llm._resolve_game_id.return_value = None
    llm.execute_query.return_value = "seen"

    memory = MemoryManager.load(tmp_path / "m.json", backend=InMemoryBackend())
    orch = Orchestrator(config, llm, memory)  # type: ignore[arg-type]

    fake_path = tmp_path / "shot.png"
    fake_path.write_bytes(b"x")
    captured = {"n": 0}

    def capture():
        captured["n"] += 1
        return fake_path, ScreenContext(foreground_title="Notepad")

    result = orch.handle_turn("what's on screen", capture_screen=capture)

    assert captured["n"] == 1
    assert result.image_path == fake_path
    assert result.answer == "seen"


def test_build_conversation_context_includes_memory(tmp_path: Path) -> None:
    config = SimpleNamespace(always_capture_screen=False)
    llm = MagicMock()
    memory = MemoryManager.load(tmp_path / "m.json", backend=InMemoryBackend())
    memory.update_from_user("remember never suggest fortnite")
    orch = Orchestrator(config, llm, memory)  # type: ignore[arg-type]
    block = orch.build_conversation_context([])
    assert "Persistent memory" in block
    assert "fortnite" in block.lower() or "remember" in block.lower()
