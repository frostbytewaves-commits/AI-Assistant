"""Определение игры и запросы к локальной базе знаний."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .minecraft_mobs import is_mob_or_drop_question, parse_mob_response


from game_data.schema import load_registry


GAME_DETECT_PROMPT = (
    "Look at this screenshot carefully.\n"
    "Which game is this?\n"
    "Reply ONE line only:\n"
    "game: minecraft\n"
    "or game: oni\n"
    "or game: other\n"
    "or game: unknown\n"
    "minecraft = blocky 3D world, hotbar, hearts/hunger.\n"
    "oni = Oxygen Not Included, side-view colony sim, duplicants, pipes, grids.\n"
    "Windows desktop, browser, IDE, or menu = other."
)


MINECRAFT_ITEM_SOURCES: dict[str, dict] = {
    "tripwire_hook": {
        "label": "Tripwire Hook",
        "primary": "Crafting is the reliable vanilla bulk source: 1 iron ingot above 1 stick above 1 plank in one vertical column -> 2 tripwire hooks.",
        "loot": [
            "Jungle temple chests can contain tripwire hooks.",
            "Pillager outpost chests can contain tripwire hooks.",
        ],
        "exploits": [
            "Tripwire hook duplication using minecarts and doors exists in some vanilla versions/setups, but it is a bug/exploit and is version/server-rule dependent.",
        ],
        "warnings": [
            "Crossbows use tripwire hooks as an ingredient; crossbows do not dismantle back into hooks in vanilla.",
            "Do not list villages, generic dungeon chests, or mob drops as tripwire hook sources unless a version-specific loot table says so.",
        ],
    },
}


@dataclass
class GameInfo:
    id: str
    name: str
    name_ru: str
    version_note: str = ""


class GameKnowledgeBase:
    def __init__(self, games_dir: Path, default_game_id: str = "") -> None:
        self.games_dir = games_dir
        self.default_game_id = default_game_id
        self._registry = self._load_registry()
        self._collection_cache: dict[str, dict[str, dict]] = {}

    def _load_registry(self) -> dict[str, GameInfo]:
        entries = load_registry(self.games_dir)
        if entries:
            return {
                gid: GameInfo(
                    id=gid,
                    name=e.name,
                    name_ru=e.name_ru,
                    version_note=e.version_note,
                )
                for gid, e in entries.items()
            }
        path = self.games_dir / "registry.json"
        if not path.exists():
            return {
                "minecraft": GameInfo("minecraft", "Minecraft", "Minecraft", "Vanilla"),
            }
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            gid: GameInfo(
                id=gid,
                name=entry.get("name", gid),
                name_ru=entry.get("name_ru", gid),
                version_note=entry.get("version_note", ""),
            )
            for gid, entry in data.items()
        }

    def _registry_raw(self) -> dict:
        path = self.games_dir / "registry.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _collection_filename(self, game_id: str, collection: str) -> str:
        raw = self._registry_raw().get(game_id, {})
        collections = raw.get("collections") or {}
        return collections.get(collection, f"{collection}.json")

    def _load_collection(self, game_id: str, collection: str) -> dict:
        cache_key = f"{game_id}:{collection}"
        if cache_key in self._collection_cache:
            return self._collection_cache[cache_key]
        path = self.games_dir / game_id / self._collection_filename(game_id, collection)
        if not path.exists():
            self._collection_cache[cache_key] = {}
            return {}
        self._collection_cache[cache_key] = json.loads(path.read_text(encoding="utf-8"))
        return self._collection_cache[cache_key]

    def _load_mobs(self, game_id: str) -> dict:
        return self._load_collection(game_id, "mobs")

    def _load_blocks(self, game_id: str) -> dict:
        return self._load_collection(game_id, "blocks")

    def _load_versions(self, game_id: str) -> dict:
        return self._load_collection(game_id, "versions")

    def _load_villager_trades(self, game_id: str) -> dict:
        return self._load_collection(game_id, "villager_trades")

    def _load_wandering_trader_trades(self, game_id: str) -> dict:
        return self._load_collection(game_id, "wandering_trader_trades")

    def _load_structures(self, game_id: str) -> dict:
        return self._load_collection(game_id, "structures")

    def _load_meta(self, game_id: str) -> dict:
        path = self.games_dir / game_id / "meta.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def get_play_version(self, game_id: str, override: str | None = None) -> str:
        if override:
            return override
        meta = self._load_meta(game_id)
        if meta.get("play_version"):
            return str(meta["play_version"])
        versions = self._load_versions(game_id)
        return str(versions.get("default_play_version", "1.21.11"))

    def _version_order(self, game_id: str) -> tuple[str, ...]:
        versions = self._load_versions(game_id)
        order = versions.get("order")
        if isinstance(order, list) and order:
            return tuple(order)
        from game_data.minecraft_versions import default_version_order
        return default_version_order()

    def _entry_available(self, entry: dict, play_version: str, game_id: str) -> bool:
        from game_data.minecraft_versions import is_available
        return is_available(entry, play_version, self._version_order(game_id))

    def _version_note(self, entry: dict, play_version: str, game_id: str) -> str:
        if self._entry_available(entry, play_version, game_id):
            return ""
        added = entry.get("added_in")
        if added:
            return f" (доступно с версии {added}, у вас {play_version})"
        removed = entry.get("removed_in")
        if removed:
            return f" (удалено в {removed})"
        return ""

    @staticmethod
    def parse_game_response(text: str) -> str | None:
        lower = text.lower()
        match = re.search(r"game:\s*(\w+)", lower)
        if match:
            gid = match.group(1).strip()
            if gid in ("minecraft", "mc"):
                return "minecraft"
            if gid in ("oni", "oxygen"):
                return "oni"
            if gid in ("other", "unknown"):
                return None
            return gid
        if "oxygen not included" in lower:
            return "oni"
        if "minecraft" in lower:
            return "minecraft"
        return None

    def get_game(self, game_id: str | None) -> GameInfo:
        gid = game_id or self.default_game_id
        if gid in self._registry:
            return self._registry[gid]
        return GameInfo(gid, gid, gid)

    def extract_mob_id(self, observation: str) -> str | None:
        mob, _ = parse_mob_response(observation)
        if mob and mob != "unknown":
            return mob
        match = re.search(r"Mob in crosshair:\s*([\w\s]+)", observation, re.I)
        if match:
            return match.group(1).strip().lower()
        return None

    def format_mob_drops(self, game_id: str, mob_id: str) -> str:
        mobs = self._load_mobs(game_id)
        entry = mobs.get(mob_id)
        if not entry:
            return f"Моб «{mob_id}» не найден в базе {game_id}."
        lines = [f"### {entry.get('name_ru', mob_id)} ({mob_id})"]
        drops = entry.get("drops", [])
        if drops:
            lines.append("**Дроп при убийстве (vanilla):**")
            for d in drops:
                note = f" — {d['note']}" if d.get("note") else ""
                lines.append(f"- {d.get('name_ru', d.get('item'))}: {d.get('count', '?')}{note}")
        else:
            lines.append("**Дроп:** нет предметов (или только опыт).")
        if entry.get("xp"):
            lines.append(f"**Опыт:** {entry['xp']}")
        if entry.get("note"):
            lines.append(f"**Примечание:** {entry['note']}")
        return "\n".join(lines)

    def _load_recipes(self, game_id: str) -> dict:
        return self._load_collection(game_id, "recipes")

    @staticmethod
    def _tokenize_question(question: str) -> list[str]:
        q = question.lower()
        tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]+", q)
        return [t for t in tokens if len(t) >= 3]

    @staticmethod
    def _is_acquisition_question(question: str) -> bool:
        q = question.lower()
        return any(
            marker in q
            for marker in (
                "get",
                "obtain",
                "farm",
                "make",
                "craft",
                "source",
                "получ",
                "фарм",
                "добы",
                "скрафт",
                "крафт",
            )
        )

    @staticmethod
    def _item_query_intent(question: str) -> str:
        q = question.lower()
        if any(m in q for m in ("why", "need", "use", "purpose", "зачем", "для чего", "нуж", "использ")):
            return "usage_value"
        if any(m in q for m in ("trade", "sell", "buy", "villager", "emerald", "торг", "продать", "купить", "жител", "изумруд")):
            return "trade"
        if any(m in q for m in ("where", "find", "loot", "chest", "structure", "где", "найти", "лут", "сундук", "структур")):
            return "location_loot"
        if any(m in q for m in ("dupe", "duplicate", "exploit", "дюп", "эксплойт")):
            return "exploit"
        if any(m in q for m in ("get", "obtain", "farm", "make", "craft", "source", "получ", "фарм", "добы", "скрафт", "крафт")):
            return "acquisition"
        return "general"

    @staticmethod
    def _item_matches(item: str, q: str, tokens: set[str]) -> bool:
        item_l = item.lower()
        spaced = item_l.replace("_", " ")
        item_tokens = set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", spaced))
        return item_l in q or spaced in q or item_l in tokens or bool(item_tokens & tokens)

    def has_recipe_target_match(self, game_id: str, question: str) -> bool:
        """True when the question mentions an item that is itself a recipe output."""
        recipes = self._load_recipes(game_id)
        q = question.lower()
        tokens = set(self._tokenize_question(question))
        for key, entry in recipes.items():
            name_ru = entry.get("name_ru", "").lower()
            display = entry.get("display_name", "").lower()
            target_names = (key.replace("_", " "), key, name_ru, display)
            if any(name and (name in q or self._item_matches(name, q, tokens)) for name in target_names):
                return True
        return False

    def has_direct_recipe_match(self, game_id: str, question: str) -> bool:
        """True when the user asks to acquire an item that is itself a recipe output."""
        return self._is_acquisition_question(question) and self.has_recipe_target_match(game_id, question)

    def _matched_recipe_key(self, game_id: str, question: str) -> str | None:
        recipes = self._load_recipes(game_id)
        q = question.lower()
        tokens = set(self._tokenize_question(question))
        for key, entry in recipes.items():
            name_ru = entry.get("name_ru", "").lower()
            display = entry.get("display_name", "").lower()
            target_names = (key.replace("_", " "), key, name_ru, display)
            if any(name and (name in q or self._item_matches(name, q, tokens)) for name in target_names):
                return key
        return None

    def _find_recipes_using_item(self, game_id: str, item_key: str, *, limit: int = 8) -> list[str]:
        recipes = self._load_recipes(game_id)
        result: list[str] = []
        for key, entry in recipes.items():
            if key == item_key:
                continue
            ingredients = [str(i).lower() for i in entry.get("ingredients", [])]
            if item_key.lower() in ingredients:
                label = entry.get("display_name") or entry.get("name_ru") or key
                result.append(f"{key} ({label})")
            if len(result) >= limit:
                break
        return result

    def item_retrieval_context(self, game_id: str, question: str) -> str:
        """Gather item facts from local DB; the LLM decides how to answer by intent."""
        if game_id != "minecraft":
            return ""
        key = self._matched_recipe_key(game_id, question)
        if not key:
            return ""
        recipes = self._load_recipes(game_id)
        entry = recipes.get(key, {})
        label = entry.get("display_name") or entry.get("name_ru") or key
        intent = self._item_query_intent(question)
        lines = [
            "### Item retrieval facts",
            f"**Detected item:** {label} ({key})",
            f"**Detected user intent:** {intent}",
            "Use these facts to answer the user's actual intent. Do not treat crafting as the main answer when intent is usage_value/trade.",
        ]

        if entry:
            if entry.get("variants"):
                variant = (entry.get("variants") or [])[0]
                count = variant.get("result_count")
                suffix = f" -> {count}" if count else ""
                lines.append(f"**Direct crafting output:** {variant.get('recipe')}{suffix}")
                if variant.get("ingredients"):
                    lines.append(f"**Crafting ingredients:** {', '.join(variant['ingredients'])}")
            elif entry.get("recipe"):
                lines.append(f"**Direct crafting output:** {entry['recipe']}")
                if entry.get("ingredients"):
                    lines.append(f"**Crafting ingredients:** {', '.join(entry['ingredients'])}")
            elif entry.get("source"):
                lines.append(f"**Direct source:** {entry['source']}")

        used_in = self._find_recipes_using_item(game_id, key)
        if used_in:
            lines.append("**Used as ingredient in recipes:** " + ", ".join(used_in))

        sources = MINECRAFT_ITEM_SOURCES.get(key)
        if sources:
            if sources.get("loot"):
                lines.append("**Confirmed loot sources:** " + "; ".join(sources["loot"]))
            if sources.get("exploits"):
                lines.append("**Known exploits/dupes:** " + "; ".join(sources["exploits"]))

        trade_text = self.trade_sources_context(game_id, question)
        if trade_text:
            lines.append("**Relevant trades:**")
            lines.append(trade_text)

        structure_text = self.structures_context(game_id, question)
        if structure_text:
            lines.append("**Relevant structures/loot:**")
            lines.append(structure_text)

        lines.append(
            "Answer planning: usage_value -> lead with valuable uses/sinks/trades; acquisition -> lead with reliable sources; location_loot -> lead with structures; trade -> lead with villagers/traders."
        )
        return "\n".join(lines)

    def item_sources_context(self, game_id: str, question: str) -> str:
        if game_id != "minecraft":
            return ""
        key = self._matched_recipe_key(game_id, question)
        if not key:
            return ""
        sources = MINECRAFT_ITEM_SOURCES.get(key)
        if not sources:
            return ""
        lines = [f"### Confirmed item sources: {sources.get('label', key)}"]
        primary = sources.get("primary")
        if primary:
            lines.append(f"**Primary source:** {primary}")
        loot = sources.get("loot") or []
        if loot:
            lines.append("**Loot sources:**")
            lines.extend(f"- {item}" for item in loot)
        exploits = sources.get("exploits") or []
        if exploits:
            lines.append("**Version-dependent exploit/dupe:**")
            lines.extend(f"- {item}" for item in exploits)
        return "\n".join(lines)

    def item_source_detail(self, game_id: str | None, question: str, source_title: str) -> str:
        """Deterministic detail for a selected item source.

        This avoids turning sparse source facts into invented step-by-step guides.
        """
        if game_id != "minecraft":
            return ""
        key = self._matched_recipe_key(game_id, question)
        if not key:
            return ""
        sources = MINECRAFT_ITEM_SOURCES.get(key)
        if not sources:
            return ""

        title = source_title.lower()
        label = sources.get("label", key)
        if "craft" in title or "крафт" in title:
            primary = sources.get("primary", "")
            return (
                f"## {label}: crafting\n\n"
                f"{primary}\n\n"
                "This is the reliable vanilla bulk method. Scale it by farming the inputs; "
                "do not infer reverse-crafting from items that use this ingredient."
            )
        if "jungle" in title or "temple" in title or "храм" in title:
            return (
                f"## {label}: jungle temple loot\n\n"
                "Jungle temple chests can contain tripwire hooks. This is a confirmed vanilla loot source, "
                "but it is not a good bulk farm because each temple is one-time loot.\n\n"
                "How to find: search jungle biomes, or use `/locate structure minecraft:jungle_pyramid` if commands are allowed."
            )
        if "pillager" in title or "outpost" in title or "аванпост" in title:
            return (
                f"## {label}: pillager outpost loot\n\n"
                "Pillager outpost chests can contain tripwire hooks. This is a confirmed vanilla loot source, "
                "but it is not guaranteed and is not efficient for bulk compared with crafting.\n\n"
                "How to find: explore open overworld biomes such as plains, desert, savanna, taiga, snowy plains, meadow, grove, or cherry grove. "
                "Outposts are not generated as a guaranteed village attachment. If commands are allowed, use `/locate structure minecraft:pillager_outpost`."
            )
        if "dupe" in title or "exploit" in title or "дюп" in title:
            return (
                f"## {label}: dupe / exploit\n\n"
                "Tripwire hook duplication with minecarts and doors exists in some vanilla versions/setups, "
                "but it is a bug/exploit and depends on game version and server rules.\n\n"
                "Use this only if your world/server allows exploits. For a normal vanilla-safe answer, use crafting."
            )
        return ""

    def item_acquisition_answer(self, game_id: str | None, question: str) -> str:
        if game_id != "minecraft" or not self.has_direct_recipe_match(game_id, question):
            return ""
        key = self._matched_recipe_key(game_id, question)
        if not key:
            return ""
        recipes = self._load_recipes(game_id)
        entry = recipes.get(key, {})
        label = entry.get("display_name") or entry.get("name_ru") or key.replace("_", " ").title()
        lines = [f"## {label}: vanilla sources"]
        sources = MINECRAFT_ITEM_SOURCES.get(key)
        if sources and sources.get("primary"):
            lines.append(sources["primary"])
        elif entry.get("variants"):
            variant = (entry.get("variants") or [])[0]
            count = variant.get("result_count")
            suffix = f" -> {count} items" if count else ""
            lines.append(f"Crafting: {variant.get('recipe')}{suffix}")
            if variant.get("ingredients"):
                lines.append(f"Ingredients: {', '.join(variant['ingredients'])}")
        elif entry.get("recipe"):
            lines.append(f"Crafting: {entry['recipe']}")
            if entry.get("ingredients"):
                lines.append(f"Ingredients: {', '.join(entry['ingredients'])}")
        elif entry.get("source"):
            lines.append(f"Source: {entry['source']}")

        if sources:
            loot = sources.get("loot") or []
            if loot:
                lines.append("")
                lines.append("Other vanilla sources:")
                lines.extend(f"- {item}" for item in loot)
            exploits = sources.get("exploits") or []
            if exploits:
                lines.append("")
                lines.append("Exploit/dupe, only if allowed:")
                lines.extend(f"- {item}" for item in exploits)

        lines.append("")
        lines.append(
            "For bulk, use the reliable source first. Do not infer reverse-crafting from items that use this item as an ingredient."
        )
        return "\n".join(lines)

    def trade_sources_context(self, game_id: str, question: str) -> str:
        if game_id != "minecraft":
            return ""
        q = question.lower()
        tokens = set(self._tokenize_question(question))
        wants_trade = any(
            marker in q
            for marker in (
                "trade",
                "trader",
                "villager",
                "wandering",
                "торг",
                "жител",
                "странств",
                "купить",
                "продать",
            )
        )
        matches: list[str] = []

        for prof_id, entry in self._load_villager_trades(game_id).items():
            prof = entry.get("profession", prof_id)
            workstation = entry.get("workstation", "")
            prof_hit = prof_id.replace("_", " ") in q or prof.lower() in q
            sell_hits = [
                item for item in entry.get("sells", [])
                if self._item_matches(item.get("item", ""), q, tokens)
            ]
            buy_hits = [
                item for item in entry.get("buys", [])
                if self._item_matches(item.get("item", ""), q, tokens)
            ]
            if not (wants_trade or prof_hit or sell_hits or buy_hits):
                continue
            if prof_hit or sell_hits or buy_hits:
                lines = [f"### Villager trade: {prof}"]
                if workstation:
                    lines.append(f"**Workstation:** {workstation}")
                if sell_hits:
                    lines.append("**Sells matching item:**")
                    for item in sell_hits[:6]:
                        note = f" — {item['note']}" if item.get("note") else ""
                        lines.append(f"- {item.get('item')} ({item.get('level', '?')}) for {item.get('cost', 'emeralds')}{note}")
                if buy_hits:
                    lines.append("**Villager buys this item (use/value, not source):**")
                    for item in buy_hits[:6]:
                        note = f" — {item['note']}" if item.get("note") else ""
                        lines.append(f"- {item.get('item')} ({item.get('level', '?')}){note}")
                if prof_hit and not sell_hits and not buy_hits:
                    sells = ", ".join(i.get("item", "") for i in entry.get("sells", [])[:8])
                    buys = ", ".join(i.get("item", "") for i in entry.get("buys", [])[:8])
                    if sells:
                        lines.append(f"**Common sells:** {sells}")
                    if buys:
                        lines.append(f"**Common buys:** {buys}")
                matches.append("\n".join(lines))

        wandering = self._load_wandering_trader_trades(game_id).get("wandering_trader", {})
        if wandering:
            sell_hits = [
                item for item in wandering.get("sells", [])
                if self._item_matches(item.get("item", ""), q, tokens)
            ]
            if sell_hits or ("wandering" in q or "странств" in q):
                lines = ["### Wandering Trader trades"]
                if wandering.get("spawn", {}).get("summary"):
                    lines.append(f"**Spawn:** {wandering['spawn']['summary']}")
                if sell_hits:
                    lines.append("**Sells matching item:**")
                    for item in sell_hits[:8]:
                        note = f" — {item['note']}" if item.get("note") else ""
                        lines.append(f"- {item.get('item')} for {item.get('cost', 'emeralds')}{note}")
                else:
                    sample = ", ".join(i.get("item", "") for i in wandering.get("sells", [])[:12])
                    lines.append(f"**Example sells:** {sample}")
                matches.append("\n".join(lines))

        return "\n\n".join(matches[:5])

    def structures_context(self, game_id: str, question: str) -> str:
        if game_id != "minecraft":
            return ""
        structures = self._load_structures(game_id)
        if not structures:
            return ""
        q = question.lower()
        tokens = set(self._tokenize_question(question))
        wants_structure = any(
            marker in q
            for marker in (
                "structure",
                "loot",
                "chest",
                "find",
                "locate",
                "temple",
                "bastion",
                "village",
                "outpost",
                "структур",
                "лут",
                "сундук",
                "найти",
                "храм",
                "бастион",
                "деревн",
                "аванпост",
            )
        )
        hits: list[tuple[int, str]] = []
        for sid, entry in structures.items():
            name = entry.get("name", sid)
            haystack = " ".join(
                [
                    sid.replace("_", " "),
                    sid,
                    name,
                    " ".join(entry.get("biomes", [])),
                    " ".join(entry.get("variants", [])),
                    " ".join(entry.get("loot", [])),
                    " ".join(entry.get("notes", [])),
                ]
            ).lower()
            score = 0
            if sid.replace("_", " ") in q or sid in q or name.lower() in q:
                score += 8
            for token in tokens:
                if token in haystack:
                    score += 2
            if wants_structure and score > 0:
                score += 2
            if score <= 0:
                continue
            lines = [f"### Structure: {name} ({sid})"]
            if entry.get("dimension"):
                lines.append(f"**Dimension:** {entry['dimension']}")
            if entry.get("biomes"):
                lines.append(f"**Biomes:** {', '.join(entry['biomes'])}")
            if entry.get("variants"):
                lines.append(f"**Variants:** {', '.join(entry['variants'])}")
            if entry.get("how_to_find"):
                lines.append("**How to find:**")
                lines.extend(f"- {item}" for item in entry["how_to_find"][:4])
            if entry.get("loot"):
                matched_loot = [item for item in entry["loot"] if self._item_matches(item, q, tokens)]
                loot = matched_loot or entry["loot"][:12]
                lines.append("**Relevant loot:** " + ", ".join(loot))
            if entry.get("notes"):
                lines.append("**Notes:**")
                lines.extend(f"- {item}" for item in entry["notes"][:3])
            hits.append((score, "\n".join(lines)))
        hits.sort(key=lambda item: item[0], reverse=True)
        return "\n\n".join(block for _score, block in hits[:4])

    def acquisition_prompt_rule(self, game_id: str, question: str) -> str:
        if not self.has_direct_recipe_match(game_id, question):
            return ""
        return (
            "Item acquisition mode:\n"
            "- Use the Item retrieval facts block and answer by Detected user intent.\n"
            "- If intent is acquisition, lead with reliable sources and mention alternatives from DB.\n"
            "- If intent is usage_value, lead with uses, recipes, trades/sinks, and why the item is valuable; do not lead with how to craft it.\n"
            "- If intent is trade, lead with villagers/traders that buy/sell it.\n"
            "- If intent is location_loot, lead with structures/loot and how to find them.\n"
            "- Do not add sources that are not in the local DB/search context."
        )

    def search_recipes(self, game_id: str, question: str, *, play_version: str | None = None) -> str:
        recipes = self._load_recipes(game_id)
        play_version = play_version or self.get_play_version(game_id)
        q = question.lower()
        acquisition = self._is_acquisition_question(question)
        hits: list[tuple[int, str]] = []

        for key, entry in recipes.items():
            name_ru = entry.get("name_ru", "").lower()
            display = entry.get("display_name", "").lower()
            haystack = f"{key} {name_ru} {display} {' '.join(entry.get('ingredients', []))}"
            target_names = (key.replace("_", " "), key, name_ru, display)
            is_target = any(name and name in q for name in target_names)
            score = 0
            if is_target:
                score += 5
            for token in self._tokenize_question(question):
                if token in haystack:
                    score += 2
                    if acquisition and token in " ".join(entry.get("ingredients", [])).lower() and not is_target:
                        score -= 3
            if any(m in q for m in ("крафт", "рецепт", "craft", "recipe", "скрафт")):
                score += 1
            if acquisition and is_target:
                score += 6
            elif acquisition and not is_target and any(
                token in " ".join(entry.get("ingredients", [])).lower()
                for token in self._tokenize_question(question)
            ):
                score -= 4
            if score <= 0:
                continue
            block = self._format_recipe(key, entry, play_version, game_id)
            if "нет в вашей версии" in block:
                score -= 1
            hits.append((score, block))

        hits.sort(key=lambda x: x[0], reverse=True)
        return "\n\n".join(h[1] for h in hits[:3])

    def search_blocks(self, game_id: str, question: str, *, play_version: str | None = None) -> str:
        blocks = self._load_blocks(game_id)
        if not blocks:
            return ""
        play_version = play_version or self.get_play_version(game_id)
        q = question.lower()
        if not any(m in q for m in ("блок", "block", "сульф", "sulfur", "руда", "ore")):
            return ""
        hits: list[tuple[int, str]] = []
        for key, entry in blocks.items():
            name_ru = entry.get("name_ru", "").lower()
            display = entry.get("display_name", "").lower()
            haystack = f"{key} {name_ru} {display}"
            score = 0
            for token in self._tokenize_question(question):
                if token in haystack:
                    score += 2
            if score <= 0:
                continue
            label = entry.get("name_ru") or entry.get("display_name", key)
            ver = self._version_note(entry, play_version, game_id)
            if ver and "доступно с" in ver:
                line = f"### {label} ({key}){ver}"
            else:
                line = f"### {label} ({key})"
            if entry.get("hardness") is not None:
                line += f"\n**Прочность:** {entry['hardness']}"
            if entry.get("added_in"):
                line += f"\n**С версии:** {entry['added_in']}"
            hits.append((score, line))
        hits.sort(key=lambda x: x[0], reverse=True)
        return "\n\n".join(h[1] for h in hits[:3])

    def _format_recipe(self, key: str, entry: dict, play_version: str, game_id: str) -> str:
        lines = [f"### {entry.get('name_ru', key)}"]
        if not self._entry_available(entry, play_version, game_id):
            added = entry.get("added_in", "?")
            lines.append(f"**В вашей версии ({play_version}) нет в игре** — добавлено в {added}.")
            return "\n".join(lines)
        if entry.get("recipe"):
            lines.append(f"**Рецепт:** {entry['recipe']}")
        if entry.get("grid"):
            lines.append(f"**Сетка:** {entry['grid']}")
        if entry.get("ingredients"):
            lines.append(f"**Ингредиенты:** {', '.join(entry['ingredients'])}")
        if entry.get("variants"):
            variants = entry.get("variants") or []
            lines.append("**Варианты крафта:**")
            for idx, variant in enumerate(variants[:4], start=1):
                recipe = variant.get("recipe")
                ingredients = ", ".join(variant.get("ingredients", []))
                count = variant.get("result_count")
                suffix = f" -> {count} шт." if count else ""
                lines.append(f"- Вариант {idx}: {recipe}{suffix}")
                if ingredients:
                    lines.append(f"  Ингредиенты: {ingredients}")
        if entry.get("source"):
            lines.append(f"**Как получить:** {entry['source']}")
        lines.append(
            "**Важно:** рецепт показывает, как получить этот предмет. Если этот предмет указан "
            "ингредиентом в другом рецепте, это не означает обратный разбор того предмета."
        )
        return "\n".join(lines)

    def build_context(
        self,
        game_id: str,
        question: str,
        *,
        mob_id: str | None = None,
        observation: str = "",
        play_version: str | None = None,
    ) -> str:
        if game_id == "oni":
            from .oni_kb import build_oni_context
            return build_oni_context(self, question)

        game = self.get_game(game_id)
        play_version = play_version or self.get_play_version(game_id)
        parts = [
            f"Игра: {game.name_ru} ({game.id})",
            f"Версия игрока: {play_version}",
            f"Источник: локальная база данных, {game.version_note or 'vanilla'}",
        ]

        if not mob_id and observation:
            mob_id = self.extract_mob_id(observation)

        if is_mob_or_drop_question(question) and mob_id:
            parts.append("")
            parts.append(self.format_mob_drops(game_id, mob_id))
        elif is_mob_or_drop_question(question):
            parts.append("")
            parts.append("Моб в прицеле не опознан — дроп из базы недоступен.")

        item_retrieval = self.item_retrieval_context(game_id, question)
        if item_retrieval:
            parts.append("")
            parts.append(item_retrieval)

        recipe_block = self.search_recipes(game_id, question, play_version=play_version)
        if recipe_block:
            parts.append("")
            parts.append(recipe_block)

        item_sources = self.item_sources_context(game_id, question)
        if item_sources:
            parts.append("")
            parts.append(item_sources)

        trade_sources = self.trade_sources_context(game_id, question)
        if trade_sources:
            parts.append("")
            parts.append(trade_sources)

        structures = self.structures_context(game_id, question)
        if structures:
            parts.append("")
            parts.append(structures)

        block_info = self.search_blocks(game_id, question, play_version=play_version)
        if block_info:
            parts.append("")
            parts.append(block_info)

        if len(parts) <= 2:
            parts.append("")
            parts.append("По этому вопросу в базе нет точной записи.")

        return "\n".join(parts)

    def synthesize_prompt_rules(
        self,
        game_id: str | None = None,
        question: str = "",
        *,
        lang: str = "en",
        advisory_mode: str = "none",
    ) -> str:
        from .language import answer_language_rule

        md = answer_language_rule(lang)  # type: ignore[arg-type]
        from .intent import is_advisory_question

        if advisory_mode == "expand":
            return (
                f"{md}\n"
                "Full deep-dive for the ONE selected variant only.\n"
                "Derive the guide from mechanics: source -> trigger -> transport -> processing/kill -> collection -> bottlenecks.\n"
                "Step-by-step build/setup, materials, layout, trade-offs, common mistakes.\n"
                "Use the Game Database for exact items, recipes, mob drops, and stats.\n"
                "Do not invent exact numbers; if not in DB/search, call them typical/approximate or ask for version.\n"
                "If mods, DLC, platform, or version can change the design, state your assumption.\n"
                "For item acquisition, recipes are directional: ingredient-of is not source-of. Never infer reverse crafting or salvage.\n"
                "Do not add another ---options--- block.\n"
                + (
                    "Minecraft: XP orbs are collected by the player only — never claim furnaces, "
                    "chests, or hoppers collect XP. Never torch a spawner block itself."
                    if game_id == "minecraft"
                    else ""
                )
            )
        if advisory_mode == "brief" or is_advisory_question(question):
            return (
                f"{md}\n"
                "Brief pass only: 2-4 sentences, name variants if several exist, no step-by-step yet.\n"
                "Options should be mechanic families, not copied guide titles unless the mechanic truly matches.\n"
                "If version/platform/mod context is missing and important, state the default assumption briefly.\n"
                "For item farming, list only real output sources; do not suggest dismantling items unless explicitly supported.\n"
                "End with ---options--- block (3-4 lines: id|title|teaser) then ---end---.\n"
                "Use the Game Database for exact names when mentioned."
            )
        if game_id == "oni":
            return (
                f"{md}\n"
                "Use ONLY facts from the Game Database block for stats and names.\n"
                "Do not invent buildings, elements, or numbers.\n"
                "If DLC/planetoid/resources affect the answer, say the assumption or ask.\n"
                "If the database has no data, clearly say so."
            )
        return (
            f"{md}\n"
            "Use ONLY facts from the Game Database block.\n"
            "Do not invent items, mobs, or numbers.\n"
            "If the database has no data, clearly say that it is not in the database.\n"
            "If an item/block is unavailable in the player's version, say so explicitly.\n"
            "If mods/platform/version can change the answer, state the assumption or ask one short question.\n"
            "Vision/OCR is only for context, not a source for drops."
        )
