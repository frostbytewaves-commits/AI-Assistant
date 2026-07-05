"""Рецепты из PrismarineJS/minecraft-data."""

from __future__ import annotations

from dataclasses import dataclass, field

from .data_api import MINECRAFT_DATA_BASE, USER_AGENT, fetch_json, item_display_name, load_items, load_language, load_recipes

PRIORITY_RECIPES = (
    "diamond_pickaxe",
    "diamond",
    "iron_ingot",
    "torch",
    "crafting_table",
    "stick",
    "iron_pickaxe",
    "iron_sword",
    "bow",
    "furnace",
    "chest",
    "bed",
)

@dataclass
class RecipeEntry:
    key: str
    name_ru: str
    recipe: str | list[str] = ""
    grid: str = ""
    source: str = ""
    recipe_type: str = "shaped"
    ingredients: list[str] = field(default_factory=list)
    result_count: int = 1

def _load_items(version: str) -> tuple[dict[int, str], dict[str, dict]]:
    items_list = load_items(version)
    id_to_name = {item["id"]: item["name"] for item in items_list}
    name_to_item = {item["name"]: item for item in items_list}
    return id_to_name, name_to_item

def _shape_to_grid(in_shape: list[list[int | None]], id_to_name: dict[int, str]) -> tuple[str, str]:
    rows: list[str] = []
    symbols: dict[str, str] = {}
    letter_ord = ord("A")
    for row in in_shape:
        cells: list[str] = []
        for cell in row:
            if cell is None:
                cells.append(" ")
                continue
            name = id_to_name.get(cell, "?")
            short = name.split("_")[-1][:1].upper()
            while short in symbols and symbols[short] != name:
                letter_ord += 1
                short = chr(letter_ord)
            symbols[short] = name
            cells.append(short)
        rows.append("".join(cells))
    legend = ", ".join(f"{sym}={name}" for sym, name in sorted(symbols.items()))
    return " / ".join(rows), legend


def _find_shaped_recipe(
    recipes: dict,
    item_name: str,
    id_to_name: dict[int, str],
    *,
    prefer_ingredients: tuple[str, ...] = (),
) -> dict | None:
    target_id = next((i for i, n in id_to_name.items() if n == item_name), None)
    if target_id is None:
        return None
    candidates: list[dict] = []
    for group in recipes.values():
        if not isinstance(group, list):
            continue
        for recipe in group:
            result = recipe.get("result")
            rid = result.get("id") if isinstance(result, dict) else result
            if rid == target_id and "inShape" in recipe:
                candidates.append(recipe)
    if not candidates:
        return None
    if prefer_ingredients:
        def score(recipe: dict) -> int:
            used = {
                id_to_name.get(cell, "")
                for row in recipe.get("inShape", [])
                for cell in row
                if cell is not None
            }
            return sum(1 for ing in prefer_ingredients if ing in used)
        ranked = sorted(candidates, key=score, reverse=True)
        if score(ranked[0]) > 0:
            return ranked[0]
    return candidates[0]


def _parse_recipe_raw(
    raw: dict,
    id_to_name: dict[int, str],
    lang: dict[str, str],
    name_to_item: dict[str, dict],
) -> RecipeEntry | None:
    result = raw.get("result")
    if isinstance(result, dict):
        rid = result.get("id")
        count = result.get("count", 1)
    else:
        rid = result
        count = 1
    if rid is None:
        return None
    item_name = id_to_name.get(rid)
    if not item_name:
        return None
    item_meta = name_to_item.get(item_name, {"name": item_name, "displayName": item_name})
    from .names_ru import recipe_name_ru

    display = item_display_name(item_meta, lang)
    entry = RecipeEntry(
        key=item_name,
        name_ru=recipe_name_ru(item_name) if item_name in PRIORITY_RECIPES else display,
        result_count=int(count),
    )
    if "inShape" in raw:
        grid, legend = _shape_to_grid(raw["inShape"], id_to_name)
        if "_planks" in legend:
            legend = ", ".join(
                f"{sym}=доски" if "planks" in name else f"{sym}={name}"
                for part in legend.split(", ")
                for sym, name in [part.split("=", 1)]
            )
        entry.recipe_type = "shaped"
        entry.grid = grid
        entry.recipe = [grid, legend] if legend else [grid]
        entry.ingredients = sorted({id_to_name.get(c, "?") for row in raw["inShape"] for c in row if c})
        return entry
    if "ingredients" in raw:
        ings = [id_to_name.get(i, "?") for i in raw["ingredients"] if i is not None]
        entry.recipe_type = "shapeless"
        entry.ingredients = sorted(set(ings))
        entry.recipe = f"Без формы: {', '.join(entry.ingredients)}"
        return entry
    return None


def fetch_all_recipes(version: str = "1.21.4") -> dict[str, dict]:
    """Все рецепты крафта, ключ — id предмета-результата."""
    id_to_name, name_to_item = _load_items(version)
    lang = load_language(version)
    raw_recipes = load_recipes(version)
    by_item: dict[str, dict] = {}

    for group in raw_recipes.values():
        if not isinstance(group, list):
            continue
        for raw in group:
            parsed = _parse_recipe_raw(raw, id_to_name, lang, name_to_item)
            if not parsed:
                continue
            key = parsed.key
            variant = {
                "type": parsed.recipe_type,
                "recipe": parsed.recipe,
                "grid": parsed.grid,
                "ingredients": parsed.ingredients,
                "result_count": parsed.result_count,
            }
            if key not in by_item:
                by_item[key] = {
                    "name_ru": parsed.name_ru,
                    "display_name": parsed.name_ru,
                    "added_in": version,
                    "variants": [variant],
                }
            else:
                existing = by_item[key]["variants"]
                sig = (variant["type"], variant.get("grid"), tuple(variant["ingredients"]))
                existing_sigs = {
                    (v["type"], v.get("grid"), tuple(v.get("ingredients", []))) for v in existing
                }
                if sig not in existing_sigs:
                    existing.append(variant)
    # Основной рецепт = первый shaped или первый
    for entry in by_item.values():
        shaped = next((v for v in entry["variants"] if v["type"] == "shaped"), None)
        primary = shaped or entry["variants"][0]
        entry["recipe_type"] = primary["type"]
        entry["recipe"] = primary["recipe"]
        entry["grid"] = primary.get("grid", "")
        entry["ingredients"] = primary.get("ingredients", [])
        if len(entry["variants"]) == 1:
            del entry["variants"]
    return by_item


def fetch_priority_recipes(version: str = "1.21.4") -> list[RecipeEntry]:
    from .names_ru import recipe_name_ru

    id_to_name, _ = _load_items(version)
    recipes = load_recipes(version)
    prefer_map = {
        "crafting_table": ("oak_planks",),
        "stick": ("oak_planks",),
        "chest": ("oak_planks",),
        "torch": ("coal", "charcoal"),
        "furnace": ("cobblestone",),
    }
    skip_shaped = {"iron_ingot", "diamond"}
    source_hints = {
        "diamond": "Руда алмазов (кирка железная+), сундуки, торговля",
        "iron_ingot": "Плавка iron ore / raw iron / железных предметов в печи",
    }

    entries: list[RecipeEntry] = []
    for item_name in PRIORITY_RECIPES:
        recipe = None if item_name in skip_shaped else _find_shaped_recipe(
            recipes, item_name, id_to_name, prefer_ingredients=prefer_map.get(item_name, ()),
        )
        name_ru = recipe_name_ru(item_name)
        if recipe and "inShape" in recipe:
            grid, legend = _shape_to_grid(recipe["inShape"], id_to_name)
            if "_planks" in legend:
                legend = ", ".join(
                    f"{sym}=доски" if "planks" in name else f"{sym}={name}"
                    for part in legend.split(", ")
                    for sym, name in [part.split("=", 1)]
                )
            lines = [grid]
            if legend:
                lines.append(legend)
            entries.append(RecipeEntry(key=item_name, name_ru=name_ru, recipe=lines, grid=grid))
        elif item_name in source_hints:
            entries.append(
                RecipeEntry(key=item_name, name_ru=name_ru, recipe="", source=source_hints[item_name])
            )
    return entries
