"""Intent gating — general how-to must not become game advisory."""

from __future__ import annotations

from assistant.intent import (
    is_advisory_question,
    is_game_advisory_question,
    is_minecraft_question,
)
from assistant.game_mechanics import infer_mechanics_game


def test_kiss_not_minecraft() -> None:
    assert is_minecraft_question("Who are KISS") is False
    assert infer_mechanics_game("Who are KISS", None) is None


def test_python_howto_not_game_advisory() -> None:
    assert is_advisory_question("how to install python") is True
    assert is_game_advisory_question("how to install python") is False


def test_minecraft_farm_is_game_advisory() -> None:
    q = "how to set up an xp farm in minecraft"
    assert is_minecraft_question(q) is True
    assert is_game_advisory_question(q) is True


def test_bare_experience_not_minecraft() -> None:
    assert infer_mechanics_game("how to gain experience", None) is None
