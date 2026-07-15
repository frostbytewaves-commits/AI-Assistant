"""Recent chat history for multi-turn context."""

from __future__ import annotations

import re

ChatTurn = tuple[str, str]  # role, content


def format_chat_history(history: list[ChatTurn], *, limit: int = 8) -> str:
    if not history:
        return ""
    lines = ["Recent conversation (stay on this topic):"]
    for role, content in history[-limit:]:
        text = re.sub(r"\s+", " ", content.strip())[:500]
        if text:
            lines.append(f"{role}: {text}")
    lines.append(
        "Use the conversation above. Stay on the user's topic; "
        "do not switch to unrelated subjects. "
        "Never reply with only empty agreement — add something useful for the current topic."
    )
    return "\n".join(lines)
