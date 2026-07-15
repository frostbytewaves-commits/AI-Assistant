"""Route user requests through an LLM instead of long keyword lists."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .screen_context import ScreenContext


@dataclass
class QueryIntent:
    needs_screen: bool
    needs_web: bool
    pipeline: str  # vision_answer | vision_then_text | text_only
    focus: str  # crosshair | hud | scene | none
    hint: str = ""

    @classmethod
    def fallback_in_game(cls, question: str) -> "QueryIntent":
        return cls(
            needs_screen=True,
            needs_web=False,
            pipeline="vision_then_text",
            focus="crosshair",
            hint=question[:120],
        )

    @classmethod
    def fallback_text(cls, question: str) -> "QueryIntent":
        return cls(
            needs_screen=False,
            needs_web=False,
            pipeline="text_only",
            focus="none",
            hint=question[:120],
        )

    @classmethod
    def screen_describe(cls, question: str = "") -> "QueryIntent":
        return cls(
            needs_screen=True,
            needs_web=True,
            pipeline="vision_answer",
            focus="scene",
            hint=(question[:120] if question else "Analyze the attached screenshot"),
        )

    @classmethod
    def force_screen(cls, question: str) -> "QueryIntent":
        return cls(
            needs_screen=True,
            needs_web=False,
            pipeline="vision_then_text",
            focus="scene",
            hint=question[:120],
        )


ROUTER_SYSTEM = (
    "You are a routing model for a universal AI assistant running on the user's computer. "
    "Read the user's question as a capable assistant would: infer what they actually want, "
    "not only the surface keywords. Decide whether the assistant needs the current screen "
    "and whether it needs web search. Reply ONLY with one JSON object, no Markdown or explanation."
)

ROUTER_USER_TEMPLATE = """Context: {context}
User question: {question}

JSON fields:
- needs_screen (bool): whether a screenshot of the current screen is needed.
- needs_web (bool): whether web search would help answer better than model knowledge alone.
- pipeline (str): "text_only" | "vision_answer" | "vision_then_text"
- focus (str): "crosshair" | "hud" | "scene" | "none"
- hint (str): one short sentence describing what the user wants.

Guidance (think; do not treat as a keyword checklist):
- needs_screen=true when the answer depends on visible pixel content right now (UI text, wallpaper, HUD, Steam library tiles).
- needs_screen=false for general knowledge, explanations, planning, and when Host window inventory already answers (what apps/windows/games are open or running).
- needs_web=true when search would meaningfully improve the answer: fresher facts, lookups of people/bands/products/characters, news, prices, versions, rare names, or when you are unsure which sense of an ambiguous name the user means.
- Interpret pronouns and verbs naturally: "who" usually points to people/groups/characters; "what" may point to concepts — but use context, not rigid word rules.
- pipeline=vision_then_text when the assistant must see the screen and then reason.
- pipeline=vision_answer when a visual description or image-based answer is enough.
- pipeline=text_only when no screenshot is needed.
- focus=crosshair / hud / scene / none as fits the question.

Example: {{"needs_screen":false,"needs_web":false,"pipeline":"text_only","focus":"none","hint":"explain the topic in depth"}}"""


FOCUS_VISION_PROMPTS = {
    "crosshair": (
        "Look at the CENTER of the screenshot (crosshair). "
        "If Minecraft: name mob/block/item in crosshair. "
        "If NOT Minecraft: describe what is in the center. Do not invent game UI."
    ),
    "hud": (
        "If Minecraft: describe HUD — health, hunger, hotbar. "
        "If NOT Minecraft: describe visible UI elements only. Do not invent hearts or hunger icons."
    ),
    "scene": (
        "Describe what is clearly visible: desktop, app, game, or scene. "
        "If NOT Minecraft, say it is not Minecraft. Do not invent game elements."
    ),
    "none": "Describe only what is clearly visible and relevant to the question.",
}


def question_needs_screen(question: str) -> bool:
    """Hard override: force a screenshot when the ask clearly needs pixels.

    Prefer the LLM router for ambiguous cases. Do not treat 'what is open' /
    inventory questions as needing a screenshot — Host context covers that.
    """
    q = question.lower()
    screen_markers = (
        "на экране",
        "what's on screen",
        "whats on screen",
        "what is on screen",
        "что видно",
        "что на экране",
        "в прицеле",
        "передо мной",
        "скриншот",
        "screenshot",
        "crosshair",
        "во что поиграть",
        "что поиграть",
        "what should i play",
        "pick a game to play",
        "choose a game to play",
    )
    if any(m in q for m in screen_markers):
        return True
    text_only_markers = (
        "крафт",
        "рецепт",
        "скрафт",
        "craft",
        "recipe",
        "как сделать",
        "как получить",
        "дроп",
        "механик",
        "версии",
    )
    if any(m in q for m in text_only_markers):
        return False
    return False


def should_auto_capture_screen(question: str, *, always_capture: bool = False) -> bool:
    """Silent screenshot only when the user asked about the screen or enabled always-capture."""
    return always_capture or question_needs_screen(question)


def is_minecraft_question(question: str) -> bool:
    """Clear Minecraft topic — not everyday words like farm/experience/recipe."""
    q = question.lower()
    markers = (
        "minecraft",
        "майнкрафт",
        "майнкраф",
        "creeper",
        "крипер",
        "enderman",
        "эндермен",
        "nether",
        "незер",
        "hotbar",
        "villager",
        "житель",
        "piglin",
        "свинозомби",
        "zombified pig",
        "xp farm",
        "mob farm",
        "iron farm",
        "gold farm",
        "guardian farm",
        "enderman farm",
        "spawner",
        "redstone",
        "редстоун",
        "автоферм",
        "майн ",
    )
    if any(m in q for m in markers):
        return True
    # "майн" alone is too short; require word-ish boundary via spaces/start
    if re.search(r"(?i)(?:^|\s)майн(?:\s|$)", q):
        return True
    return False


_ADVISORY_MARKERS = (
    "how to",
    "how do i",
    "how should",
    "how can i",
    "best way",
    "optimize",
    "optimiz",
    "efficient",
    "efficiency",
    "setup",
    "set up",
    "build a",
    "build an",
    "build my",
    "design",
    "improve",
    "strategy",
    "advice",
    "recommend",
    "what should i",
    "early game",
    "mid game",
    "late game",
    "system",
    " loop",
    "manage",
    "deal with",
    "fix my",
    "help me",
    "как ",
    "как мне",
    "как лучше",
    "как постро",
    "как сделать",
    "как настро",
    "оптимиз",
    "настро",
    "постро",
    "систем",
    "совет",
    "улучш",
    "эффектив",
    "ранняя игра",
    "что делать",
    "вариант",
    "guide",
    "tutorial",
)

def continuation_user_payload(question: str) -> str:
    """If this is a follow-up wrapper, return original topic + user line only."""
    lower_full = question.lower()
    if "earlier question:" not in lower_full or "user follow-up:" not in lower_full:
        return question.strip()
    topic = ""
    follow = ""
    for line in question.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("earlier question:"):
            topic = stripped.split(":", 1)[1].strip()
        elif low.startswith("user follow-up:"):
            follow = stripped.split(":", 1)[1].strip()
    return f"{topic} {follow}".strip() or question.strip()


def is_advisory_question(question: str) -> bool:
    """How-to / optimize phrasing — not automatically a game strategy request."""
    # Judge only the user's topic/follow-up — never continuation boilerplate.
    q = continuation_user_payload(question).lower()
    return any(m in q for m in _ADVISORY_MARKERS)


def is_supported_game_topic(question: str) -> bool:
    """True when wording clearly points at a supported game (not everyday vocabulary)."""
    return is_minecraft_question(question) or is_oni_question(question)


def is_game_advisory_question(
    question: str,
    *,
    game_id: str | None = None,
    active_game: str | None = None,
) -> bool:
    """Game strategy deep-dive UI — only with real game context + how-to phrasing."""
    if not (game_id or active_game or is_supported_game_topic(question)):
        return False
    return is_advisory_question(question)


def is_oni_strategy_question(question: str) -> bool:
    """Deprecated alias — use is_game_advisory_question for ONI context."""
    return is_game_advisory_question(question) and (
        is_oni_question(question)
        or any(
            w in question.lower()
            for w in ("duplicant", "geyser", "electrolyzer", "spom", "aquatuner")
        )
    )


def is_oni_question(question: str) -> bool:
    """Clear Oxygen Not Included topic — avoid everyday words (oxygen, stress, colony)."""
    q = question.lower()
    markers = (
        "oxygen not included",
        "oxygennotincluded",
        " duplicant",
        "duplicants",
        "electrolyzer",
        "oxylite",
        "natural gas geyser",
        "cool steam geyser",
        "drecko",
        "dreckos",
        "puft",
        "polluted oxygen",
        "meal lice",
        "sleet wheat",
        "bristle blossom",
        "carbon skimmer",
        "spom",
        "aquatuner",
        "steam turbine",
        "slickster",
        "shine bug",
        "critter ranch",
        "liquid lock",
        "gas pipe",
        "liquid pipe",
    )
    if any(m in q for m in markers):
        return True
    # Bare "oni" only as a whole word (not "online", "onion", etc.)
    if re.search(r"(?i)(?:^|\s)oni(?:\s|$)", q):
        return True
    return False


SCREEN_CAPTURE_DEFAULT_PROMPT = (
    "The user captured a screenshot but did not type a specific question. "
    "Look at the image and respond with whatever is most helpful for what you see:\n"
    "- Game (Minecraft, Oxygen Not Included, etc.): contextual advice — base problems, "
    "what they are looking at, suggested next steps.\n"
    "- Error dialog or app issue: explain it and how to fix it.\n"
    "- Game launcher / library: summarize visible titles; offer a recommendation only if obvious.\n"
    "- Desktop or browser: briefly describe the scene; identify characters or content if relevant.\n"
    "Do not say you lack a question — infer intent from the screenshot. "
    "End with one line offering to go deeper on a specific topic."
)


def effective_screen_question(question: str) -> str:
    q = question.strip()
    return q if q else SCREEN_CAPTURE_DEFAULT_PROMPT


def plan_attached_screen_query(question: str, ctx: ScreenContext) -> QueryIntent:
    """Route a user question that already has a captured screenshot attached."""
    q = question.strip()
    if not q:
        if ctx.minecraft_window:
            return QueryIntent(
                needs_screen=True,
                needs_web=False,
                pipeline="vision_then_text",
                focus="crosshair",
                hint="Infer what the player needs from the Minecraft view.",
            )
        if ctx.oni_window:
            return QueryIntent(
                needs_screen=True,
                needs_web=False,
                pipeline="vision_then_text",
                focus="scene",
                hint="Colony view — spot issues and suggest practical next steps.",
            )
        if ctx.active_game:
            return QueryIntent(
                needs_screen=True,
                needs_web=False,
                pipeline="vision_then_text",
                focus="scene",
                hint="Game screen — give contextual advice for what is visible.",
            )
        return QueryIntent(
            needs_screen=True,
            needs_web=True,
            pipeline="vision_answer",
            focus="scene",
            hint="No text question — describe and assist with what's on screen.",
        )

    if ctx.active_game:
        focus = "crosshair" if ctx.minecraft_window else "scene"
        return QueryIntent(
            needs_screen=True,
            needs_web=is_advisory_question(q) or is_minecraft_question(q),
            pipeline="vision_then_text",
            focus=focus,
            hint=q[:120],
        )

    ql = q.lower()
    needs_web = any(m in ql for m in (
        "who is", "who's", "what is", "identify", "кто это", "что это", "what's this",
        "error code", "news", "price",
    ))
    pipeline = "vision_then_text" if any(m in ql for m in (
        "how", "why", "fix", "help", "should i", "как", "почему", "исправ", "ошиб", "что делать",
    )) else "vision_answer"
    return QueryIntent(
        needs_screen=True,
        needs_web=needs_web or question_needs_screen(q),
        pipeline=pipeline,
        focus="scene",
        hint=q[:120],
    )
