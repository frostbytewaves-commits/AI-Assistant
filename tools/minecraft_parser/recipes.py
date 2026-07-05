"""Рецепты из PrismarineJS/minecraft-data."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

MINECRAFT_DATA_BASE = (
    "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data/pc"
)
USER_AGENT = "AI-Assistant-MinecraftParser/1.0"

# Приоритетные рецепты для ассистента (id предмета в minecraft-data)
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
    recipe: str
    grid: str = ""
    source: str = ""


def _fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_items(version: str) -> tuple[dict[int, str], dict[str, dict]]:
    items_list = _fetch_json(f"{MINECRAFT_DATA_BASE}/{version}/items.json")
    id_to_name: dict[int, str] = {}
    name_to_item: dict[str, dict] = {}
    for item in items_list:
        id_to_name[item["id"]] = item["name"]
        name_to_item[item["name"]] = item
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
    grid_text = " / ".join(rows)
    return grid_text, legend


def _find_shaped_recipe(
    recipes: dict,
    item_name: str,
    id_to_name: dict[int, str],
    *,
    prefer_ingredients: tuple[str, ...] = (),
) -> dict | None:
    target_id = None
    for item_id, name in id_to_name.items():
        if name == item_name:
            target_id = item_id
            break
    if target_id is None:
        return None

    candidates: list[dict] = []
    for group in recipes.values():
        if not isinstance(group, list):
            continue
        for recipe in group:
            result = recipe.get("result")
            rid = result.get("id") if isinstance(result, dict) else result
            if rid != target_id:
                continue
            if "inShape" in recipe:
                candidates.append(recipe)

    if not candidates:
        return None

    def score(recipe: dict) -> tuple[int, int]:
        used = {
            id_to_name.get(cell, "")
            for row in recipe.get("inShape", [])
            for cell in row
            if cell is not None
        }
        prefer_hits = sum(1 for ing in prefer_ingredients if ing in used)
        generic_hits = sum(1 for name in used if name.endswith("_planks") or name in ("stick", "coal", "charcoal"))
        return (prefer_hits, generic_hits)

    if prefer_ingredients:
        ranked = sorted(candidates, key=score, reverse=True)
        if score(ranked[0])[0] > 0:
            return ranked[0]

    return candidates[0]


def fetch_priority_recipes(version: str = "1.21.4") -> list[RecipeEntry]:
    from .names_ru import recipe_name_ru

    id_to_name, _ = _load_items(version)
    recipes = _fetch_json(f"{MINECRAFT_DATA_BASE}/{version}/recipes.json")

    entries: list[RecipeEntry] = []
    prefer_map = {
        "crafting_table": ("oak_planks",),
        "stick": ("oak_planks",),
        "chest": ("oak_planks",),
        "torch": ("coal", "charcoal"),
        "furnace": ("cobblestone",),
    }
    skip_shaped = {"iron_ingot", "diamond"}

    for item_name in PRIORITY_RECIPES:
        if item_name in skip_shaped:
            recipe = None
        else:
            recipe = _find_shaped_recipe(
                recipes,
                item_name,
                id_to_name,
                prefer_ingredients=prefer_map.get(item_name, ()),
            )
        key = item_name
        name_ru = recipe_name_ru(key)

        if recipe and "inShape" in recipe:
            grid, legend = _shape_to_grid(recipe["inShape"], id_to_name)
            if "_planks" in legend:
                legend = ", ".join(
                    f"{sym}=доски" if "planks" in name else f"{sym}={name}"
                    for part in legend.split(", ")
                    for sym, name in [part.split("=", 1)]
                )
            recipe_lines = [grid]
            if legend:
                recipe_lines.append(legend)
            entries.append(
                RecipeEntry(
                    key=key,
                    name_ru=name_ru,
                    recipe=recipe_lines,
                    grid=grid,
                )
            )
            continue

        # Предметы без крафта — только источник
        source_hints = {
            "diamond": "Руда алмазов (кирка железная+), сундуки, торговля",
            "iron_ingot": "Плавка iron ore / raw iron / железных предметов в печи",
        }
        if item_name in source_hints:
            entries.append(
                RecipeEntry(
                    key=key,
                    name_ru=name_ru,
                    recipe="",
                    source=source_hints[item_name],
                )
            )

    return entries
