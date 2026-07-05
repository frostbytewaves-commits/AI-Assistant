import re

_ANIME_CUES = re.compile(
    r"\b(anime|аниме|cartoon|мульт|manga|wallpaper|обои|cowboy bebop|bebop)\b",
    re.IGNORECASE,
)
_CHARACTER_CUES = re.compile(
    r"\b(character|персонаж|smoking|сигарет|cigarette|spaceship|косм|spike|spiegel)\b",
    re.IGNORECASE,
)
_VISUAL_STOP = re.compile(
    r"\b(the|and|with|this|that|screen|screenshot|desktop|image|visible|likely|"
    r"appears|shows|showing|there|here|some|very|also|just|only|not|maybe|"
    r"экран|видно|скриншот|рабоч|стол|вероятно|похоже)\b",
    re.IGNORECASE,
)


def build_search_query(
    question: str,
    ocr_text: str = "",
    *,
    minecraft_context: bool = False,
    oni_context: bool = False,
    vision_hint: str = "",
) -> str:
    query = question.strip()
    if vision_hint:
        query = f"{vision_hint} {query}".strip()
    if ocr_text and not ocr_text.startswith("[OCR"):
        title_match = re.search(r"(?m)^([A-Z][\w\s\-]{2,40})$", ocr_text[:800])
        if title_match:
            snippet = title_match.group(1).strip()
            if snippet.lower() not in query.lower():
                query = f"{snippet} {query}"
    lower = query.lower()
    if oni_context and "oxygen not included" not in lower and "oni" not in lower:
        query = f"oxygen not included {query}"
    elif minecraft_context and "minecraft" not in lower and "майнкрафт" not in lower:
        query = f"minecraft {query}"
    return query[:220]


def _extract_visual_keywords(observation: str, max_words: int = 8) -> list[str]:
    if not observation:
        return []
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9\-']{3,}", observation)
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        lower = word.lower()
        if _VISUAL_STOP.search(word):
            continue
        if lower in seen:
            continue
        seen.add(lower)
        keywords.append(word)
        if len(keywords) >= max_words:
            break
    return keywords


def build_screen_search_query(question: str, vision_observation: str, ocr_text: str = "") -> str:
    """Поиск для «что на экране» — без привязки к Minecraft."""
    obs = (vision_observation or "").strip()
    base = question.strip() or "what is on screen"
    anime_cues = bool(_ANIME_CUES.search(obs))
    character_cues = bool(_CHARACTER_CUES.search(obs))
    lower_obs = obs.lower()
    smoking_anime_cues = anime_cues and any(
        cue in lower_obs
        for cue in ("cigarette", "smoking", "smoke", "сигар", "курит")
    )

    if smoking_anime_cues:
        keywords = _extract_visual_keywords(obs, max_words=5)
        query_parts = [*keywords[:4], "Cowboy Bebop Spike Spiegel smoking anime wallpaper"]
        query = " ".join(query_parts)
    elif anime_cues or character_cues:
        keywords = _extract_visual_keywords(obs)
        query_parts = keywords[:6]
        if not query_parts:
            query_parts = [base]
        query_parts.append("anime wallpaper character identify")
        query = " ".join(query_parts)
    else:
        parts = [base]
        if obs:
            snippet = obs[:280] if len(obs) > 280 else obs
            parts.append(snippet)
        if ocr_text and not ocr_text.startswith("[OCR"):
            parts.append(ocr_text[:180])
        query = " ".join(p for p in parts if p)

    query = re.sub(r"\s+", " ", query).strip()
    query = re.sub(r"(?i)\bminecraft\b", "", query).strip()
    return query[:220]


def web_search(query: str, max_results: int = 5, timeout_sec: int = 8) -> str:
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return ""

    def _search_impl() -> str:
        lines: list[str] = []
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        for index, item in enumerate(results, start=1):
            title = item.get("title", "")
            body = item.get("body", "")
            href = item.get("href", "")
            lines.append(f"{index}. {title}\n   {body}\n   {href}")
        return "\n\n".join(lines) if lines else ""

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_search_impl)
        try:
            return future.result(timeout=timeout_sec)
        except (FuturesTimeout, Exception):
            return ""
