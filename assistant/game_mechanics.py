"""Formula-style game reasoning rules.

This module is intentionally not a bank of finished answers.  It provides
mechanical invariants and reusable formulas so the LLM can derive an answer
instead of memorizing one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MechanicsPack:
    game_id: str
    aliases: tuple[str, ...]
    principles: tuple[str, ...]
    formulas: tuple[str, ...]
    invalid_assumptions: tuple[str, ...] = ()
    advisory_focus: tuple[str, ...] = ()


UNIVERSAL_REASONING_RULES = (
    "Universal game reasoning protocol:",
    "1. Identify the game and the exact mechanic the user is asking about.",
    "2. Separate sources, transformations, constraints, player actions, and outputs.",
    "3. Build the answer from mechanics: source -> trigger/condition -> transport -> conversion/kill -> collection -> bottleneck.",
    "4. If a mechanic is unknown, say what is unknown and ask/search; do not fill gaps with mechanics from another game.",
    "5. Screen/video context is only evidence of what is visible, not proof that the user is playing or asking about that game.",
    "6. For farms/systems, reason in terms of: spawn/generation rule, activation area, rate limit, transport, collection, failure modes.",
    "7. Validate the plan against impossible mechanics before answering.",
)


SOURCE_AND_CONFIDENCE_RULES = (
    "Source and confidence rules:",
    "- Treat Game Database facts as strongest local evidence for exact names, drops, recipes, and stats.",
    "- Treat Game Mechanics formulas as reasoning scaffolding, not complete documentation.",
    "- Treat web/search/wiki snippets as freshness evidence, especially for patches, DLCs, mods, and current version changes.",
    "- Do not invent exact numbers. Use DB/search numbers, or say the value is approximate/unknown.",
    "- If rules and search conflict, mention the conflict and prefer the more specific/current source.",
    "- Rejected/invalid assumptions are internal checks. Do not list them in the final answer unless the user asked about that exact false method.",
)


VERSION_AND_MOD_RULES = (
    "Version/mod rules:",
    "- Default to vanilla/base game first.",
    "- Do not include mods, DLC, expansions, datapacks, or server-specific mechanics unless the user explicitly confirmed them in memory or the current message.",
    "- If mods/DLC might be relevant, ask one short confirmation question after giving the vanilla baseline, or before modded-only advice.",
    "- Ask or qualify when Java vs Bedrock, DLC, expansion, beta branch, or mods can change the answer.",
    "- If the user says vanilla, modded, DLC, seed, server, or version, keep that constraint through the answer.",
    "- If the user asks for exploits, bugs, or edge tech, say they are version-dependent.",
    "- Do not reject a mechanic just because the base-game formula pack lacks it; first check whether the user may mean a mod, datapack, DLC, or patch change.",
)


CLARIFICATION_RULES = (
    "Clarification policy:",
    "- If the game or mechanic is ambiguous and a wrong assumption would change the answer, ask one short clarifying question.",
    "- If a useful default exists, state the assumption briefly and answer under that assumption.",
    "- If the user corrects you, keep the topic and revise the mechanics instead of repeating the previous answer.",
    "- For unsupported games, give a high-level reasoning framework and ask for version/mod/source rather than pretending expertise.",
)


MINECRAFT = MechanicsPack(
    game_id="minecraft",
    aliases=("minecraft", "майнкрафт"),
    principles=(
        "Minecraft systems are made from world rules: spawning, random ticks, redstone updates, entity AI, fluids, block states, and player actions.",
        "A farm is not a fixed build; it is a pipeline: generate target -> move target -> process target -> collect outputs -> prevent competing spawns.",
        "Drops come from entity death or block/item actions. Exact drops/recipes must come from the Game Database when available.",
        "Recipes are directional: if item X is an ingredient for item Y, that does not imply Y can be disassembled back into X.",
        "Item acquisition must come from one of the game's actual sources: crafting output, block drop, mob drop, loot container, trading/bartering, or explicit salvage mechanic.",
        "XP is a separate output from item drops. XP appears as orbs and is collected by the player touching the orbs.",
        "Player-kill credit matters for many XP farms. Fully environmental kills often give items but not useful player XP.",
        "Hoppers, chests, water streams, and minecarts move items; they do not collect XP orbs.",
        "Furnaces can store XP from their own smelting operations only; they do not store mob XP.",
        "Java, Bedrock, servers, datapacks, and mods can change farm viability; qualify advice when platform/version is unknown.",
    ),
    formulas=(
        "Mob XP farm = valid spawn source + dark/valid spawn space + pathing or water transport + player-credit kill zone + item collection + cave lighting.",
        "Spawner grinder = active player near spawner + valid 9x9-ish spawn volume + darkness + transport away from spawner + player finishing hit.",
        "Portal/piglin XP farm = portal-based spawn source + fast funnel/aggro/kill chamber + player pickup path + gold item storage.",
        "Guardian XP farm = monument spawn rules + water/funnel control + kill chamber + player last-hit or pickup access.",
        "Enderman XP farm = End spawning platform + aggro/funnel mechanic + controlled kill platform + player pickup access.",
        "Crop farm = growth rule (random ticks + light + hydration when relevant) + harvest mechanism + replant limitation + item transport.",
        "Iron farm = villager/golem spawning conditions + valid spawn platform + panic/work/sleep constraints by version + golem kill + item storage.",
        "Bulk item acquisition = identify renewable source + check whether target is craft output/drop/loot/trade + scale inputs or source rate + reject reverse-crafting unless explicit.",
        "Redstone build = input signal + state memory if needed + timing + update order + output actuator + reset path.",
    ),
    invalid_assumptions=(
        "Do not claim hoppers/chests/furnaces collect mob XP.",
        "Do not put torches on a spawner in an active grinder; that disables spawning.",
        "Do not recommend crop/wheat/sugar farms as XP farms unless the method is a furnace-smelting XP bank.",
        "Do not assume Java and Bedrock farms are identical; mention version/platform uncertainty when relevant.",
        "Do not reject modded mechanics if the user explicitly says they use mods; ask which mod or answer with a caveat.",
        "Do not invent disassembly/salvage/recycling. Vanilla Minecraft has no general item dismantling mechanic.",
        "Do not claim broken tools/weapons return their crafting ingredients unless DB/search explicitly says so.",
    ),
    advisory_focus=(
        "For Minecraft advice, present the mechanic first, then variants. Keep exact block counts conservative unless sourced.",
        "When user says XP, prioritize player-kill mob farms, furnace XP banks only when smelting is explicitly relevant.",
    ),
)


ONI = MechanicsPack(
    game_id="oni",
    aliases=("oxygen not included", "oxygennotincluded"),
    principles=(
        "ONI is a conservation and routing game: mass, heat, power, gas pressure, liquid flow, and automation thresholds drive systems.",
        "A system is a loop: input resource -> machine conversion -> output products/heat -> storage/removal -> automation control.",
        "Gases separate by density and pressure; CO2 sinks, hydrogen rises, oxygen fills breathable space.",
        "Heat problems require heat capacity, thermal conductivity, phase changes, and coolant routing, not magic deletion.",
        "Duplicant labor, morale, pathing, and downtime are part of system throughput.",
        "DLC, planetoid type, tech stage, and available geysers/resources can change the best design.",
    ),
    formulas=(
        "Gas management = source rate + density behavior + pressure limits + pump/filter routing + deletion/conversion/storage.",
        "Oxygen system = water/algae/rust input + oxygen producer + byproduct handling + pressure control + heat control + power budget.",
        "Power system = generator fuel source + heat/CO2 byproducts + smart battery automation + wire capacity + backup storage.",
        "Cooling loop = heat source + coolant path + heat exchanger + deletion sink (AETN/turbine/space) + automation threshold.",
        "Ranching loop = critter food + grooming/labor + room constraints + eggs/byproducts + population automation.",
    ),
    invalid_assumptions=(
        "Do not say Deodorizer removes CO2; it handles polluted oxygen.",
        "Do not ignore heat and byproducts when recommending machines.",
        "Do not invent building stats; use the Game Database for numbers.",
        "Do not pretend one fixed blueprint fits every colony; state the resource/tech assumptions.",
    ),
    advisory_focus=(
        "For ONI advice, include early/mid/late alternatives and the limiting resource for each.",
        "Always mention byproducts and automation when they are part of the system.",
    ),
)


NOITA = MechanicsPack(
    game_id="noita",
    aliases=("noita", "нойта"),
    principles=(
        "Noita progression is not XP/level based. It is based on wands, spells, perks, health upgrades, knowledge, and biome exploration.",
        "Do not transfer RPG or Minecraft mechanics into Noita.",
        "If the user asks for XP in Noita, correct the premise and explain the actual progression systems.",
        "Mods can add systems that vanilla Noita does not have; ask which mod if the user insists a mechanic exists.",
    ),
    formulas=(
        "Noita progression = survive biome -> find wand/spells -> edit wand where allowed -> collect health/perks -> manage liquids/materials -> descend or explore.",
        "Noita build advice = wand stats + spell modifiers + mana/recharge/delay + risk control + biome threats.",
    ),
    invalid_assumptions=(
        "No traditional XP points, XP orbs, quests, or character levels.",
        "Do not claim enemies drop XP.",
        "Do not deny a clearly stated modded mechanic without asking for the mod.",
    ),
)


PACKS: tuple[MechanicsPack, ...] = (MINECRAFT, ONI, NOITA)


def _matches(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def infer_mechanics_game(question: str, active_game: str | None = None) -> str | None:
    """Infer a mechanics pack, without treating background video as gameplay."""
    if active_game:
        return active_game
    lower = question.lower()
    for pack in PACKS:
        if _matches(lower, pack.aliases):
            return pack.game_id
    # Strong Minecraft cues only — bare "xp"/"farm"/"experience" false-positive on life topics.
    minecraft_hints = (
        "spawner",
        "piglin",
        "guardian farm",
        "enderman farm",
        "iron farm",
        "gold farm",
        "mob farm",
        "xp farm",
        "redstone",
        "villager",
        "nether portal",
        "creeper",
        "автоферм",
    )
    if _matches(lower, minecraft_hints):
        return "minecraft"
    oni_hints = (
        "duplicant",
        "electrolyzer",
        "slickster",
        "spom",
        "aquatuner",
        "oxylite",
        "drecko",
        "meal lice",
    )
    if _matches(lower, oni_hints):
        return "oni"
    return None


def looks_like_game_question(question: str) -> bool:
    """True only when the user is clearly talking about a game (not everyday how-tos)."""
    lower = question.lower()
    if infer_mechanics_game(question, None) is not None:
        return True
    markers = (
        "gameplay",
        "in-game",
        "in game",
        "this game",
        "the game",
        "boss fight",
        "loot table",
        "skill tree",
        "crafting recipe",
        "геймплей",
        "в игре",
        "эта игра",
        "этой игре",
        "лут",
        "крафт рецепт",
    )
    return _matches(lower, markers)


def _select_lines(lines: tuple[str, ...], question: str, *, max_lines: int) -> list[str]:
    lower = question.lower()
    keywords = [w for w in lower.replace("/", " ").split() if len(w) >= 3]
    scored: list[tuple[int, str]] = []
    for line in lines:
        line_lower = line.lower()
        score = sum(1 for kw in keywords if kw in line_lower)
        scored.append((score, line))
    selected = [line for score, line in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    if len(selected) < max_lines:
        for line in lines:
            if line not in selected:
                selected.append(line)
            if len(selected) >= max_lines:
                break
    return selected[:max_lines]


def build_mechanics_context(
    question: str,
    *,
    game_id: str | None = None,
    active_game: str | None = None,
    advisory_mode: str = "none",
) -> str:
    """Return compact formula rules relevant to the question."""
    resolved = game_id or infer_mechanics_game(question, active_game)
    parts: list[str] = ["Game Mechanics Formula Layer"]
    parts.extend(UNIVERSAL_REASONING_RULES)
    parts.extend(SOURCE_AND_CONFIDENCE_RULES)
    parts.extend(VERSION_AND_MOD_RULES)
    parts.extend(CLARIFICATION_RULES)

    pack = next((p for p in PACKS if p.game_id == resolved), None)
    if not pack:
        parts.extend(
            (
                "No game-specific formula pack matched. Use only provided DB/search/screen evidence.",
                "If the question needs game-specific mechanics, ask which game/version or say the data is missing.",
            )
        )
        return "\n".join(parts)

    parts.append(f"Resolved mechanics pack: {pack.game_id}")
    parts.append("Principles:")
    parts.extend(f"- {line}" for line in _select_lines(pack.principles, question, max_lines=5))
    parts.append("Reusable formulas:")
    parts.extend(f"- {line}" for line in _select_lines(pack.formulas, question, max_lines=6))
    if pack.invalid_assumptions:
        parts.append("Internal invalid-assumption checks (do not repeat in final answer unless user asked):")
        parts.extend(f"- {line}" for line in pack.invalid_assumptions)
    if advisory_mode in {"brief", "expand"} and pack.advisory_focus:
        parts.append("Advisory answer focus:")
        parts.extend(f"- {line}" for line in pack.advisory_focus)
    return "\n".join(parts)
