"""Распознавание мобов Minecraft на скрине."""

import re

# Vanilla Java mob ids (English, lowercase)
VANILLA_MOBS = frozenset({
    "allay", "armadillo", "axolotl", "bat", "bee", "blaze", "bogged", "breeze",
    "camel", "cat", "cave spider", "chicken", "cod", "cow", "creeper", "dolphin",
    "donkey", "drowned", "elder guardian", "ender dragon", "enderman", "endermite",
    "evoker", "fox", "frog", "ghast", "giant", "glow squid", "goat", "guardian",
    "hoglin", "horse", "husk", "iron golem", "llama", "magma cube", "mooshroom",
    "mule", "ocelot", "panda", "parrot", "phantom", "pig", "piglin", "piglin brute",
    "pillager", "polar bear", "pufferfish", "rabbit", "ravager", "salmon", "sheep",
    "shulker", "silverfish", "skeleton", "slime", "sniffer", "snow golem", "spider",
    "squid", "stray", "strider", "tadpole", "trader llama", "tropical fish", "turtle",
    "vex", "villager", "vindicator", "wandering trader", "warden", "witch", "wither",
    "wither skeleton", "wolf", "zoglin", "zombie", "zombie villager", "zombified piglin",
})

# Ошибки слабых vision-моделей → vanilla
MOB_CORRECTIONS = {
    "ursa": "sheep",
    "bear": "polar bear",
    "lamb": "sheep",
    "ram": "sheep",
    "bull": "cow",
    "calf": "cow",
    "piglet": "pig",
    "chick": "chicken",
    "puppy": "wolf",
    "kitten": "cat",
    "steve": "villager",
    "alex": "villager",
    "monster": None,
    "animal": None,
    "mob": None,
    "creature": None,
    "unknown": None,
}

MOB_IDENTIFY_PROMPT = (
    "Minecraft Java screenshot. Look at the CENTER (crosshair).\n"
    "What passive or hostile MOB is the player looking at?\n"
    "Reply EXACTLY in this format (one line):\n"
    "mob: <english_name>\n"
    "look: <white wool / pink pig / green creeper / etc, max 6 words>\n"
    "Use ONLY real vanilla mob names: cow, sheep, pig, chicken, zombie, skeleton, "
    "creeper, spider, enderman, villager, wolf, horse, rabbit, fox, bee, etc.\n"
    "If not a mob or unclear: mob: unknown"
)


def parse_mob_response(text: str) -> tuple[str | None, str]:
    mob: str | None = None
    look = ""
    for line in text.splitlines():
        line = line.strip()
        lower = line.lower()
        if lower.startswith("mob:"):
            mob = line.split(":", 1)[1].strip().lower()
        elif lower.startswith("look:"):
            look = line.split(":", 1)[1].strip()
    if not mob:
        match = re.search(
            r"\b(cow|sheep|pig|chicken|zombie|skeleton|creeper|spider|enderman|"
            r"villager|wolf|horse|rabbit|fox|bee|mooshroom|goat|llama|cat|ocelot|"
            r"polar bear|panda|dolphin|squid|salmon|cod|turtle|axolotl|frog|"
            r"iron golem|snow golem|phantom|witch|blaze|ghast|slime|silverfish|"
            r"piglin|hoglin|strider|warden|camel|sniffer|armadillo)\b",
            text,
            re.I,
        )
        if match:
            mob = match.group(1).lower()
    return mob, look


def _fuzzy_in_vanilla(name: str) -> str | None:
    n = name.lower().strip()
    if n in VANILLA_MOBS:
        return n
    if n in MOB_CORRECTIONS:
        return MOB_CORRECTIONS[n]
    for vanilla in VANILLA_MOBS:
        if n == vanilla:
            return vanilla
        if len(n) >= 4 and (n in vanilla or vanilla in n):
            if abs(len(n) - len(vanilla)) <= 2:
                return vanilla
    return None


def normalize_mob_observation(raw: str) -> str:
    mob, look = parse_mob_response(raw)
    if mob:
        corrected = MOB_CORRECTIONS.get(mob, mob)
        if corrected and corrected in VANILLA_MOBS:
            desc = f"Mob in crosshair: {corrected}"
            if look:
                desc += f" ({look})"
            return desc
        fuzzy = _fuzzy_in_vanilla(mob)
        if fuzzy:
            return f"Mob in crosshair: {fuzzy}" + (f" ({look})" if look else "")

    # По описанию внешности
    lower = raw.lower()
    look_hints = (
        ("white wool", "sheep"),
        ("wool sheep", "sheep"),
        ("pink pig", "pig"),
        ("black and white cow", "cow"),
        ("green creeper", "creeper"),
    )
    for hint, name in look_hints:
        if hint in lower or (look and hint in look.lower()):
            return f"Mob in crosshair: {name} (by appearance: {hint})"

    return f"Vision uncertain. Raw: {raw[:200]}"


def is_mob_or_drop_question(question: str) -> bool:
    q = question.lower()
    markers = (
        "выпад", "дроп", "drop", "лут", "loot", "моб", "животн", "падает",
        "даёт", "дает", "убить", "фарм", "с этого", "с него", "с неё",
    )
    return any(m in q for m in markers)
