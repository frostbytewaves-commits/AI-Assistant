"""Brief advisory answers with selectable deep-dive follow-ups."""

from __future__ import annotations

import re

OPTIONS_BLOCK_RE = re.compile(
    r"---options---\s*(.*?)\s*---end---",
    re.DOTALL | re.IGNORECASE,
)


TYPO_FIXES: dict[str, str] = {
    "frams": "farms",
    "farns": "farms",
    "frm": "farm",
    "iot": "it",
    "exp": "xp",
}

FOLLOWUP_MARKERS = (
    "what about",
    "how about",
    "tell me more",
    "more about",
    "what if",
    "instead",
    "too slow",
    "kinda slow",
    "kind of slow",
    "slow though",
    "and farms",
    "about farms",
    "about frams",
    "the first",
    "the second",
    "option ",
    "вариант",
    "а если",
    "медлен",
    "ферм",
    "про ферм",
)

REJECTION_MARKERS = (
    "nah",
    "nope",
    "not using",
    "aren't using",
    "arent using",
    "isn't using",
    "isnt using",
    "not that",
    "wrong",
    "don't mean",
    "dont mean",
    "didn't mean",
    "didnt mean",
    "не то",
    "не про",
    "не это",
)

CLARIFICATION_MARKERS = (
    "i mean",
    "i'm speaking",
    "im speaking",
    "speaking about",
    "speaking bout",
    "talking about",
    "talking bout",
    "actually",
    "specifically",
    "я про",
    "имею в виду",
)


def normalize_followup_text(text: str) -> str:
    result = text
    for typo, fix in TYPO_FIXES.items():
        result = re.sub(rf"\b{re.escape(typo)}\b", fix, result, flags=re.IGNORECASE)
    return result


def strip_false_pick_prompt(text: str) -> str:
    """Remove model-written 'pick an option' lines when no options block was parsed."""
    return re.sub(
        r"\n*\*?\*?(?:Want details\?|Pick an option below)[^\n]*\*?\*?\s*",
        "\n",
        text,
        flags=re.IGNORECASE,
    ).strip()


def is_conversation_followup(question: str, topic: str) -> bool:
    if not topic or not question.strip():
        return False
    q = normalize_followup_text(question.lower().strip())
    if any(m in q for m in FOLLOWUP_MARKERS):
        return True
    if any(m in q for m in REJECTION_MARKERS):
        return True
    if any(m in q for m in CLARIFICATION_MARKERS):
        return True
    if len(q) < 100 and any(
        w in q for w in ("farm", "farms", "xp", "build", "setup", "that", "those", "they", "it")
    ):
        return True
    if len(q) < 60:
        return True
    return False


def build_continuation_message(
    topic: str,
    follow_up: str,
    *,
    prior_brief: str = "",
    game_id: str | None = None,
) -> str:
    follow_up = normalize_followup_text(follow_up)
    parts = [f"Earlier question: {topic}"]
    if prior_brief:
        parts.append(f"Your earlier brief answer:\n{prior_brief[:700]}")
    parts.append(f"User follow-up: {follow_up}")
    if game_id:
        parts.append(f"Game context: {game_id}")
        parts.append(
            "Continue the SAME game conversation. "
            "'frams' means farms (in-game builds), never FPS/frames/performance. "
            "If the user wants farm/build variants, give a brief answer and a mandatory "
            "---options--- block with 3-4 specific variants."
        )
        combined = (topic + " " + follow_up).lower()
        if any(w in combined for w in ("xp", "experience", "level", "опыт", "уровн")):
            parts.append(
                "Topic is XP/experience. Recommend mob/orb XP farms (piglin, guardian, "
                "spawner grinder, enderman). NOT crop/wheat/sugar farms, NOT fishing "
                "rods or enchanting tables as the main answer."
            )
    else:
        parts.append(
            "Continue the SAME non-game topic from the earlier question and your brief answer. "
            "Do not switch to Minecraft, games, farms, or unrelated subjects. "
            "For 'tell me more', add useful detail in a few short paragraphs or bullets — "
            "stay on the original subject."
        )
    if any(m in follow_up.lower() for m in REJECTION_MARKERS):
        parts.append(
            "User rejected your previous suggestions. Do NOT repeat them. "
            "Offer different concrete variants"
            + (" with a fresh ---options--- block." if game_id else ".")
        )
    if any(m in follow_up.lower() for m in CLARIFICATION_MARKERS):
        parts.append(
            "User is clarifying what they meant. Narrow your answer to their "
            "exact intent — do not give generic alternatives."
        )
    return "\n".join(parts)


def parse_options_block(block: str) -> list[dict]:
    options: list[dict] = []
    for line in block.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        opt_id = parts[0].lstrip("[").rstrip("]")
        title = parts[1]
        teaser = parts[2] if len(parts) > 2 else ""
        if title:
            options.append({"id": opt_id, "title": title, "teaser": teaser})
    return options


def extract_followup_options(text: str) -> tuple[str, list[dict]]:
    match = OPTIONS_BLOCK_RE.search(text)
    if not match:
        return strip_false_pick_prompt(text.strip()), []
    options = parse_options_block(match.group(1))
    display = (text[: match.start()] + text[match.end() :]).strip()
    display = re.sub(r"\n{3,}", "\n\n", display)
    display = strip_false_pick_prompt(display)
    if options:
        display = display.rstrip() + "\n\n**Want details?** Pick an option below."
    return display, options


def match_followup_selection(question: str, options: list[dict]) -> dict | None:
    if not options:
        return None
    q = normalize_followup_text(question.strip())
    if not q:
        return None
    ql = q.lower()

    num_match = re.match(r"^(?:option\s*)?(\d+)$", ql)
    if num_match:
        idx = int(num_match.group(1))
        for opt in options:
            if str(opt["id"]) == str(idx):
                return opt

    for prefix in ("вариант ", "option ", "expand ", "details on ", "подробнее про ", "про "):
        if ql.startswith(prefix):
            rest = q[len(prefix) :].strip().lower()
            for opt in options:
                if rest in opt["title"].lower() or opt["title"].lower() in rest:
                    return opt

    for opt in options:
        title_l = opt["title"].lower()
        if ql == title_l or title_l in ql or ql in title_l:
            return opt
    return None


def build_expansion_prompt(
    topic: str,
    option: dict,
    *,
    game_id: str | None = None,
    curated_guide: str = "",
) -> str:
    title = option["title"]
    teaser = option.get("teaser", "")
    parts = [
        f"Original question: {topic}",
        f"Selected deep-dive variant: {title}",
    ]
    if game_id:
        parts.append(f"Game context: {game_id}")
    if teaser:
        parts.append(f"Variant summary: {teaser}")
    if curated_guide:
        parts.append("Authoritative guide outline (keep all facts; you may reformat only):")
        parts.append(curated_guide[:4000])
    parts.append(
        "Give the FULL step-by-step build/setup guide for ONLY this selected variant. "
        "Include materials, layout, dimensions if relevant, and common mistakes. "
        "Do not invent mechanics that contradict the outline above."
    )
    return "\n".join(parts)
