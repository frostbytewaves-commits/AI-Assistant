"""Парсер Minecraft — плагин для game_db_parser."""

from __future__ import annotations

from ...core.base import GameParser, PopulateContext, PopulateResult
from ...core.io import load_json, write_json
from ...core.registry import register_parser
from .blocks import build_blocks_db
from .names_ru import item_name_ru, mob_name_ru
from .recipes import RecipeEntry, fetch_all_recipes, fetch_priority_recipes
from .versions import build_versions_manifest
from .wiki import MobWikiData, fetch_mobs
from .wiki_versions import fetch_wiki_supplements

VANILLA_MOBS = (
    "allay", "armadillo", "axolotl", "bat", "bee", "blaze", "bogged", "breeze",
    "camel", "cat", "cave spider", "chicken", "cod", "cow", "creeper", "dolphin",
    "donkey", "drowned", "elder guardian", "ender dragon", "enderman", "endermite",
    "evoker", "fox", "frog", "ghast", "glow squid", "goat", "guardian",
    "hoglin", "horse", "husk", "iron golem", "llama", "magma cube", "mooshroom",
    "mule", "ocelot", "panda", "parrot", "phantom", "pig", "piglin", "piglin brute",
    "pillager", "polar bear", "pufferfish", "rabbit", "ravager", "salmon", "sheep",
    "shulker", "silverfish", "skeleton", "slime", "sniffer", "snow golem", "spider",
    "squid", "stray", "strider", "tadpole", "trader llama", "tropical fish", "turtle",
    "vex", "villager", "vindicator", "wandering trader", "warden", "witch", "wither",
    "wither skeleton", "wolf", "zoglin", "zombie", "zombie villager", "zombified piglin",
)


def _mob_to_entry(mob: MobWikiData, existing: dict | None) -> dict:
    existing = existing or {}
    entry: dict = {
        "name_ru": existing.get("name_ru") or mob_name_ru(mob.mob_id),
        "drops": [],
    }
    if mob.xp:
        entry["xp"] = mob.xp
    elif existing.get("xp"):
        entry["xp"] = existing["xp"]
    if mob.drops:
        entry["drops"] = [
            {
                "item": d.item,
                "name_ru": item_name_ru(d.item),
                "count": d.count,
                **({"note": d.note} if d.note else {}),
            }
            for d in mob.drops
        ]
    elif existing.get("drops") is not None:
        entry["drops"] = existing["drops"]
    if existing.get("note"):
        entry["note"] = existing["note"]
    return entry


def _recipe_to_entry(recipe: RecipeEntry, existing: dict | None) -> dict:
    existing = existing or {}
    entry: dict = {"name_ru": recipe.name_ru or existing.get("name_ru", "")}
    if recipe.recipe:
        entry["recipe"] = recipe.recipe
    elif existing.get("recipe") and not recipe.source:
        entry["recipe"] = existing["recipe"]
    if recipe.grid:
        entry["grid"] = recipe.grid
    elif existing.get("grid") and not recipe.source:
        entry["grid"] = existing["grid"]
    if recipe.source:
        entry["source"] = recipe.source
        entry.pop("recipe", None)
        entry.pop("grid", None)
    elif existing.get("source"):
        entry["source"] = existing["source"]
    return entry


@register_parser
class MinecraftParser(GameParser):
    game_id = "minecraft"

    def available_collections(self) -> list[str]:
        return [
            "mobs",
            "recipes",
            "blocks",
            "versions",
            "villager_trades",
            "wandering_trader_trades",
            "structures",
        ]

    def populate(self, ctx: PopulateContext) -> PopulateResult:
        result = PopulateResult()
        targets = ctx.collections or self.available_collections()
        if "versions" in targets:
            self._populate_versions(ctx, result)
        if "blocks" in targets:
            self._populate_blocks(ctx, result)
        if "mobs" in targets:
            self._populate_mobs(ctx, result)
        if "recipes" in targets:
            self._populate_recipes(ctx, result)
        for name in ("villager_trades", "wandering_trader_trades", "structures"):
            if name in targets:
                self._populate_static_collection(ctx, result, name)
        return result

    def _populate_versions(self, ctx: PopulateContext, result: PopulateResult) -> None:
        from .data_api import TRACKED_DATA_VERSIONS

        play_ver = str(ctx.options.get("play_version", "1.21.11"))
        manifest = build_versions_manifest(
            default_play_version=play_ver,
            data_versions=list(TRACKED_DATA_VERSIONS),
        )
        write_json(ctx.game_dir / "versions.json", manifest)

        meta_path = ctx.game_dir / "meta.json"
        meta = load_json(meta_path) if meta_path.exists() else {}
        meta["play_version"] = play_ver
        collections = meta.setdefault("collections", {})
        collections.update({
            "mobs": {"file": "mobs.json", "description_ru": "Мобы и дроп"},
            "recipes": {"file": "recipes.json", "description_ru": "Рецепты крафта"},
            "blocks": {"file": "blocks.json", "description_ru": "Блоки"},
            "versions": {"file": "versions.json", "description_ru": "Версии"},
            "villager_trades": {"file": "villager_trades.json", "description_ru": "Торговля жителей"},
            "wandering_trader_trades": {"file": "wandering_trader_trades.json", "description_ru": "Торги странствующего торговца"},
            "structures": {"file": "structures.json", "description_ru": "Структуры, поиск, варианты и лут"},
        })
        write_json(meta_path, meta)
        result.updated["versions"] = 1
        result.processed["versions"] = 1

    def _populate_static_collection(self, ctx: PopulateContext, result: PopulateResult, name: str) -> None:
        path = ctx.game_dir / f"{name}.json"
        if not path.exists():
            write_json(path, {})
            result.updated[name] = 1
            result.processed[name] = 0
            result.errors.append(f"{name}: создан пустой файл; заполните статические данные вручную")
            return
        data = load_json(path)
        result.processed[name] = len(data) if isinstance(data, dict) else 0
        result.updated[name] = 0

    def _populate_blocks(self, ctx: PopulateContext, result: PopulateResult) -> None:
        version = str(ctx.options.get("version", "1.21.11"))
        include_wiki = ctx.options.get("wiki_versions", True) and not ctx.options.get("offline")
        wiki: dict = {}
        if include_wiki:
            try:
                wiki = fetch_wiki_supplements()
            except Exception as exc:
                result.errors.append(f"blocks/wiki: {exc}")
        blocks, changes = build_blocks_db(max_version=version, wiki_supplements=wiki)
        if not blocks:
            result.errors.append(
                f"blocks: не удалось загрузить данные (проверьте интернет). "
                f"Попробуйте: --offline --collections recipes --version {version}"
            )
            return
        existing = load_json(ctx.game_dir / "blocks.json")
        updated = 0
        for key, entry in blocks.items():
            merged = {**entry, **{k: v for k, v in existing.get(key, {}).items() if k in ("name_ru", "note")}}
            if merged != existing.get(key):
                updated += 1
            existing[key] = merged
        write_json(ctx.game_dir / "blocks.json", existing)
        write_json(ctx.game_dir / "version_changes.json", changes)
        result.processed["blocks"] = len(blocks)
        result.updated["blocks"] = updated

    def _populate_mobs(self, ctx: PopulateContext, result: PopulateResult) -> None:
        path = ctx.game_dir / "mobs.json"
        existing = load_json(path)
        mob_filter = ctx.options.get("mob_filter") or list(VANILLA_MOBS)
        delay = float(ctx.options.get("delay_sec", 0.35))
        to_fetch = [mid for mid in mob_filter if not ctx.only_missing or mid not in existing]
        result.processed["mobs"] = len(to_fetch)
        updated = 0
        for mob in fetch_mobs(to_fetch, delay_sec=delay):
            if mob.error and not mob.drops:
                result.errors.append(f"mobs/{mob.mob_id}: {mob.error}")
            merged = _mob_to_entry(mob, existing.get(mob.mob_id))
            if merged != existing.get(mob.mob_id):
                updated += 1
            existing[mob.mob_id] = merged
        write_json(path, existing)
        result.updated["mobs"] = updated

    def _populate_recipes(self, ctx: PopulateContext, result: PopulateResult) -> None:
        path = ctx.game_dir / "recipes.json"
        existing = load_json(path)
        version = str(ctx.options.get("version", "1.21.11"))
        full = ctx.options.get("full_recipes", True)

        try:
            if full:
                fetched = fetch_all_recipes(version=version)
            else:
                fetched = None
        except Exception as exc:
            result.errors.append(f"recipes: {exc}")
            return

        if full:
            fetched = fetched or {}
            updated = 0
            for key, entry in fetched.items():
                old = existing.get(key, {})
                merged = {**entry, **{k: v for k, v in old.items() if k in ("name_ru", "note", "source")}}
                if merged != old:
                    updated += 1
                existing[key] = merged
            write_json(path, existing)
            result.processed["recipes"] = len(fetched)
            result.updated["recipes"] = updated
        else:
            recipes = fetch_priority_recipes(version=version)
            updated = 0
            for recipe in recipes:
                merged = _recipe_to_entry(recipe, existing.get(recipe.key))
                if merged != existing.get(recipe.key):
                    updated += 1
                existing[recipe.key] = merged
            write_json(path, existing)
            result.processed["recipes"] = len(recipes)
            result.updated["recipes"] = updated
