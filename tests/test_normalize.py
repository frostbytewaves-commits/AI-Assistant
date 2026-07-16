"""Tool normalize: desktop apps over web URLs."""

from __future__ import annotations

from assistant.act.types import ActionRequest
from plugins.system.normalize import normalize_action_request, resolve_launch_id


def test_resolve_tg_alias() -> None:
    assert resolve_launch_id("tg") == "telegram"
    assert resolve_launch_id("тг") == "telegram"


def test_open_url_telegram_becomes_launch(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.system.normalize.find_window",
        lambda *a, **k: None,
    )
    req = normalize_action_request(
        ActionRequest(action="open_url", args={"url": "https://t.me"}, confidence=0.9)
    )
    assert req.action == "launch_app"
    assert req.args["id"] == "telegram"


def test_focus_tg_without_native_becomes_launch(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.system.normalize.find_window",
        lambda *a, **k: None,
    )
    req = normalize_action_request(
        ActionRequest(action="focus_window", args={"query": "tg"}, confidence=0.9)
    )
    assert req.action == "launch_app"
    assert req.args["id"] == "telegram"


def test_focus_telegram_when_native_open(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.system.normalize.find_window",
        lambda *a, **k: {"title": "Telegram", "process_name": "Telegram.exe", "hwnd": 1},
    )
    req = normalize_action_request(
        ActionRequest(action="focus_window", args={"query": "telegram"}, confidence=0.9)
    )
    assert req.action == "focus_window"
    assert req.args["query"] == "telegram"
