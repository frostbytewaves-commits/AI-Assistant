"""Decide whether the user wants a whitelist tool — model proposes, code executes."""

from __future__ import annotations

ACTION_PLANNER_SYSTEM = (
    "You route desktop tool requests for a local assistant. "
    "Default to action=none. Only choose tools when the user clearly orders actions NOW. "
    "Reply ONLY with one JSON object. No markdown."
)

ACTION_PLANNER_USER = """Available tools:
{catalog}

{host_hint}

Plugin notes:
{plugin_notes}

User: {question}

JSON shapes:
{{"action":"none","confidence":0.0}}
or one step:
{{"action":"<tool_name>","args":{{...}},"confidence":0.0-1.0}}
or several steps (order matters, max 5):
{{"steps":[{{"action":"...","args":{{...}}}},{{"action":"...","args":{{...}}}}],"confidence":0.0-1.0}}

Rules:
- DEFAULT none for questions, chat, explanations, "what is open".
- Clear imperatives only: open/launch/focus/close/mute/play/pause/open url.
- For MULTIPLE asks in one message, return steps[] with ALL of them.
- Never invent action names or args. Use only the catalog (and arg schemas).
- Prefer desktop apps over websites when the catalog/plugin notes say so.
- If unsure → action=none.
- confidence must be >= 0.75 to run; otherwise none.
"""
