"""Action plan parser tests."""

from __future__ import annotations

from assistant.act.planner import parse_action_plan


def test_parse_none() -> None:
    assert parse_action_plan('{"action":"none","confidence":0.0}') == []


def test_parse_single_action() -> None:
    reqs = parse_action_plan(
        '{"action":"launch_app","args":{"id":"telegram"},"confidence":0.9}'
    )
    assert len(reqs) == 1
    assert reqs[0].action == "launch_app"
    assert reqs[0].args["id"] == "telegram"
    assert reqs[0].confidence == 0.9


def test_parse_steps_inherits_confidence() -> None:
    raw = """
    {
      "steps": [
        {"action": "focus_window", "args": {"query": "vpn"}},
        {"action": "launch_app", "args": {"id": "telegram"}}
      ],
      "confidence": 0.88
    }
    """
    reqs = parse_action_plan(raw)
    assert len(reqs) == 2
    assert reqs[0].action == "focus_window"
    assert reqs[0].confidence == 0.88
    assert reqs[1].action == "launch_app"


def test_parse_markdown_fence() -> None:
    raw = """```json
{"action":"volume_mute","args":{},"confidence":0.8}
```"""
    reqs = parse_action_plan(raw)
    assert len(reqs) == 1
    assert reqs[0].action == "volume_mute"


def test_parse_garbage() -> None:
    assert parse_action_plan("not json") == []
    assert parse_action_plan("") == []
