"""Сборка и запись JSON-базы для GameKnowledgeBase."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .names_ru import item_name_ru, mob_name_ru
from .recipes import RecipeEntry, fetch_priority_recipes
from .wiki import MobWikiData, fetch_mobs

# Список vanilla-мобов совпадает с assistant/minecraft_mobs.py
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


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mob_to_entry(mob: MobWikiData, existing: dict | None) -> dict:
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
    if mob.error and not mob.drops:
        entry.setdefault("_parser_warning", mob.error)

    return entry


def recipe_to_entry(recipe: RecipeEntry, existing: dict | None) -> dict:
    existing = existing or {}
    entry: dict = {"name_ru": recipe.name_ru or existing.get("name_ru", "")}
    if recipe.recipe:
        entry["recipe"] = recipe.recipe if isinstance(recipe.recipe, list) else recipe.recipe
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


def populate_mobs(
    output_path: Path,
    mob_ids: list[str],
    *,
    only_missing: bool = False,
    delay_sec: float = 0.35,
) -> tuple[int, int, list[str]]:
    existing = _load_json(output_path)
    to_fetch = [
        mid for mid in mob_ids
        if not only_missing or mid not in existing
    ]
    fetched = fetch_mobs(to_fetch, delay_sec=delay_sec)

    updated = 0
    errors: list[str] = []
    for mob in fetched:
        if mob.error and not mob.drops:
            errors.append(f"{mob.mob_id}: {mob.error}")
        merged = mob_to_entry(mob, existing.get(mob.mob_id))
        if merged != existing.get(mob.mob_id):
            updated += 1
        existing[mob.mob_id] = {k: v for k, v in merged.items() if not k.startswith("_")}

    _write_json(output_path, existing)
    return len(to_fetch), updated, errors


def populate_recipes(
    output_path: Path,
    *,
    version: str = "1.21.4",
) -> int:
    existing = _load_json(output_path)
    recipes = fetch_priority_recipes(version=version)
    updated = 0
    for recipe in recipes:
        merged = recipe_to_entry(recipe, existing.get(recipe.key))
        if merged != existing.get(recipe.key):
            updated += 1
        existing[recipe.key] = merged
    _write_json(output_path, existing)
    return updated


def run(
    games_dir: Path,
    *,
    mobs: bool = True,
    recipes: bool = True,
    mob_filter: list[str] | None = None,
    only_missing: bool = False,
    version: str = "1.21.4",
    delay_sec: float = 0.35,
) -> int:
    game_dir = games_dir / "minecraft"
    mob_ids = mob_filter or list(VANILLA_MOBS)
    exit_code = 0

    if mobs:
        print(f"Загрузка {len(mob_ids)} мобов с minecraft.wiki …")
        count, updated, errors = populate_mobs(
            game_dir / "mobs.json",
            mob_ids,
            only_missing=only_missing,
            delay_sec=delay_sec,
        )
        print(f"  Обработано: {count}, обновлено записей: {updated}")
        for err in errors:
            print(f"  ! {err}")
        if errors:
            exit_code = 1

    if recipes:
        print(f"Загрузка рецептов из minecraft-data {version} …")
        n = populate_recipes(game_dir / "recipes.json", version=version)
        print(f"  Обновлено рецептов: {n}")

    print(f"Готово: {game_dir}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    root = Path(__file__).resolve().parents[2]
    default_games = root / "data" / "games"

    parser = argparse.ArgumentParser(
        description="Парсер Minecraft: заполняет data/games/minecraft/*.json для AI-ассистента.",
    )
    parser.add_argument(
        "--games-dir",
        type=Path,
        default=default_games,
        help="Папка data/games (по умолчанию: %(default)s)",
    )
    parser.add_argument("--mobs-only", action="store_true", help="Только mobs.json")
    parser.add_argument("--recipes-only", action="store_true", help="Только recipes.json")
    parser.add_argument(
        "--mob",
        action="append",
        dest="mobs",
        metavar="ID",
        help="Один моб (можно несколько раз): sheep, zombie, iron golem",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Не перезаписывать уже существующие мобы",
    )
    parser.add_argument(
        "--version",
        default="1.21.4",
        help="Версия minecraft-data для рецептов",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Пауза между запросами к wiki (сек)",
    )
    args = parser.parse_args(argv)

    do_mobs = not args.recipes_only
    do_recipes = not args.mobs_only

    return run(
        args.games_dir,
        mobs=do_mobs,
        recipes=do_recipes,
        mob_filter=args.mobs,
        only_missing=args.only_missing,
        version=args.version,
        delay_sec=args.delay,
    )


if __name__ == "__main__":
    sys.exit(main())
