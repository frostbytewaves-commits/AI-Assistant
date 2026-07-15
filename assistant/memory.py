"""Persistent assistant memory.

The memory is intentionally small and conservative: it stores user/game
preferences and confirmed constraints, not raw chat logs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_MEMORY: dict[str, Any] = {
    "user_preferences": {
        "answer_style": "brief_first",
        "assume_vanilla": True,
        "require_mod_confirmation": True,
    },
    "games": {
        "minecraft": {
            "edition": "unknown",
            "version": "unknown",
            "vanilla_confirmed": True,
            "mods_confirmed": False,
            "dlc_confirmed": False,
        },
        "oni": {
            "dlc_confirmed": False,
            "vanilla_confirmed": True,
        },
        "noita": {
            "mods_confirmed": False,
            "vanilla_confirmed": True,
        },
    },
    "corrections": [],
    "pending_confirmation": None,
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _detect_game(text: str) -> str | None:
    lower = text.lower()
    if any(m in lower for m in ("minecraft", "майнкрафт", "bedrock edition", "java edition")):
        return "minecraft"
    if re.search(r"(?i)(?:^|\s)майн(?:\s|$)", lower):
        return "minecraft"
    if "oxygen not included" in lower or "oxygennotincluded" in lower:
        return "oni"
    if re.search(r"(?i)(?:^|\s)oni(?:\s|$)", lower):
        return "oni"
    if any(m in lower for m in ("noita", "нойта")):
        return "noita"
    return None


def _truthy_mod_confirmation(text: str) -> bool:
    lower = text.lower()
    positive = (
        "with mods",
        "modded",
        "i use mods",
        "with dlc",
        "dlc enabled",
        "expansion",
        "с модами",
        "модами",
        "модовый",
        "с дополнениями",
        "длс",
        "dlc",
    )
    negative = (
        "without mods",
        "without dlc",
        "no mods",
        "no dlc",
        "vanilla",
        "без мод",
        "без дополн",
        "без dlc",
        "ванил",
    )
    return any(p in lower for p in positive) and not any(n in lower for n in negative)


def _short_yes(text: str) -> bool:
    lower = _compact(text).lower()
    return lower in {"yes", "yeah", "yep", "да", "ага", "угу", "ок", "ok"}


def _short_no(text: str) -> bool:
    lower = _compact(text).lower()
    return lower in {"no", "nope", "нет", "не", "nah"}


def _vanilla_confirmation(text: str) -> bool:
    lower = text.lower()
    return any(
        marker in lower
        for marker in (
            "vanilla",
            "без мод",
            "без дополн",
            "ванил",
            "чистая версия",
            "base game",
        )
    )


def _edition(text: str) -> str | None:
    lower = text.lower()
    if "java" in lower or "джава" in lower:
        return "Java"
    if "bedrock" in lower or "бедрок" in lower:
        return "Bedrock"
    return None


def _version(text: str) -> str | None:
    match = re.search(r"\b(?:1\.\d+(?:\.\d+)?|2\.\d+(?:\.\d+)?)\b", text)
    return match.group(0) if match else None


@dataclass
class AssistantMemory:
    path: Path
    data: dict[str, Any] = field(default_factory=lambda: json.loads(json.dumps(DEFAULT_MEMORY)))

    @classmethod
    def load(cls, path: Path) -> "AssistantMemory":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                data = _deep_merge(DEFAULT_MEMORY, loaded)
                return cls(path=path, data=data)
            except Exception:
                return cls(path=path)
        memory = cls(path=path)
        memory.save()
        return memory

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def update_from_user(self, text: str, *, fallback_game: str | None = None) -> None:
        cleaned = _compact(text)
        if not cleaned:
            return
        game = _detect_game(cleaned) or fallback_game
        changed = False
        pending = self.data.get("pending_confirmation")

        if pending and isinstance(pending, dict) and game is None:
            game = pending.get("game")

        if game:
            game_mem = self.data.setdefault("games", {}).setdefault(game, {})
            edition = _edition(cleaned)
            version = _version(cleaned)
            if edition and game == "minecraft":
                game_mem["edition"] = edition
                changed = True
            if version and game == "minecraft":
                game_mem["version"] = version
                changed = True
            if _vanilla_confirmation(cleaned):
                game_mem["vanilla_confirmed"] = True
                game_mem["mods_confirmed"] = False
                game_mem["dlc_confirmed"] = False
                self.data["pending_confirmation"] = None
                changed = True
            elif _truthy_mod_confirmation(cleaned) or (
                pending and isinstance(pending, dict) and _short_yes(cleaned)
            ):
                game_mem["vanilla_confirmed"] = False
                pending_kind = pending.get("kind") if isinstance(pending, dict) else ""
                if (
                    "dlc" in cleaned.lower()
                    or "длс" in cleaned.lower()
                    or "дополн" in cleaned.lower()
                    or pending_kind in {"dlc", "non_vanilla"}
                ):
                    game_mem["dlc_confirmed"] = True
                if pending_kind in {"mods", "non_vanilla"} or not game_mem.get("dlc_confirmed"):
                    game_mem["mods_confirmed"] = True
                self.data["pending_confirmation"] = None
                changed = True
            elif pending and isinstance(pending, dict) and _short_no(cleaned):
                game_mem["vanilla_confirmed"] = True
                game_mem["mods_confirmed"] = False
                game_mem["dlc_confirmed"] = False
                self.data["pending_confirmation"] = None
                changed = True

        correction_markers = (
            "remember",
            "запомни",
            "не предлагай",
            "never suggest",
            "всегда",
            "always",
        )
        if any(marker in cleaned.lower() for marker in correction_markers):
            corrections = self.data.setdefault("corrections", [])
            if cleaned not in corrections:
                corrections.append(cleaned[:300])
                self.data["corrections"] = corrections[-20:]
                changed = True

        if changed:
            self.save()

    def note_assistant_message(self, text: str, *, fallback_game: str | None = None) -> None:
        cleaned = _compact(text)
        lower = cleaned.lower()
        if "?" not in cleaned:
            return
        asks_mods = any(m in lower for m in ("mod", "мод"))
        asks_dlc = any(m in lower for m in ("dlc", "длс", "дополн", "expansion"))
        if not asks_mods and not asks_dlc:
            return
        game = _detect_game(cleaned) or fallback_game
        if not game:
            return
        kind = "non_vanilla"
        if asks_mods and not asks_dlc:
            kind = "mods"
        elif asks_dlc and not asks_mods:
            kind = "dlc"
        self.data["pending_confirmation"] = {"game": game, "kind": kind}
        self.save()

    def format_context(self) -> str:
        prefs = self.data.get("user_preferences", {})
        games = self.data.get("games", {})
        corrections = self.data.get("corrections", [])
        lines = ["Persistent memory and defaults:"]
        lines.append(
            "- You are a general desktop assistant with optional game expertise when games are relevant."
        )
        if prefs.get("assume_vanilla", True):
            lines.append(
                "- When giving GAME advice: assume vanilla/base game. Do not use mods, DLC, expansions, "
                "datapacks, or servers unless the user explicitly confirmed them."
            )
        if prefs.get("require_mod_confirmation", True):
            lines.append(
                "- If mods/DLC could matter for a game answer, ask one short confirmation before "
                "giving modded/DLC-specific advice."
            )
        for game, values in sorted(games.items()):
            details: list[str] = []
            if values.get("edition") and values.get("edition") != "unknown":
                details.append(f"edition={values['edition']}")
            if values.get("version") and values.get("version") != "unknown":
                details.append(f"version={values['version']}")
            details.append(f"vanilla={bool(values.get('vanilla_confirmed', True))}")
            details.append(f"mods={bool(values.get('mods_confirmed', False))}")
            details.append(f"dlc={bool(values.get('dlc_confirmed', False))}")
            lines.append(f"- {game}: " + ", ".join(details))
        if corrections:
            lines.append("User corrections to keep:")
            lines.extend(f"- {item}" for item in corrections[-8:])
        return "\n".join(lines)
