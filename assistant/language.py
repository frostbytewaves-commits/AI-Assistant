"""Detect question language and build matching reply / UI strings."""

from __future__ import annotations

import re
from typing import Literal

Lang = Literal["en", "ru"]

_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_LATIN = re.compile(r"[A-Za-z]")

LANGUAGE_MATCH_RULE = (
    "Reply in the same language as the user's question: "
    "English question → English answer; Russian question → Russian answer. "
    "Do not mix languages in the reply unless the user does."
)

TTS_VOICE_EN = "en-US-GuyNeural"
TTS_VOICE_RU = "ru-RU-DmitryNeural"


def detect_response_language(text: str) -> Lang:
    """Infer reply language from the user's question (or transcript)."""
    if not text or not text.strip():
        return "en"
    cyr = len(_CYRILLIC.findall(text))
    lat = len(_LATIN.findall(text))
    if cyr == 0:
        return "en"
    if lat == 0:
        return "ru"
    if cyr >= lat:
        return "ru"
    # Mixed: Russian only if Cyrillic is a clear majority
    if cyr >= 4 and cyr >= lat * 0.4:
        return "ru"
    return "en"


def resolve_response_language(text: str, mode: str = "auto") -> Lang:
    if mode == "ru":
        return "ru"
    if mode == "en":
        return "en"
    return detect_response_language(text)


def answer_language_rule(lang: Lang) -> str:
    if lang == "ru":
        return "Answer in Russian using Markdown."
    return "Answer in English using Markdown."


def tts_voice_for_language(lang: Lang, *, default_en: str = TTS_VOICE_EN) -> str:
    return TTS_VOICE_RU if lang == "ru" else default_en


def game_database_header(lang: Lang) -> str:
    return "=== База данных игры ===" if lang == "ru" else "=== Game Database ==="
