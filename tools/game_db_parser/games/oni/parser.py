"""Парсер Oxygen Not Included — oxygennotincluded.wiki.gg."""

from __future__ import annotations

import time
from pathlib import Path

from ...core.base import GameParser, PopulateContext, PopulateResult
from ...core.io import load_json, write_json
from ...core.registry import register_parser
from .categories import COLLECTIONS, SKIP_PREFIXES, SKIP_TITLES
from .wiki import (
    entry_to_dict,
    fetch_wikitext_batch,
    list_category_pages,
    parse_guide_page,
    parse_page,
)

_BUNDLED_TOPICS = Path(__file__).parent / "topics.json"


def _should_skip(title: str, skip_prefixes: tuple[str, ...] = SKIP_PREFIXES) -> bool:
    if title in SKIP_TITLES:
        return True
    return any(title.startswith(p) for p in skip_prefixes)


def _unique_titles(
    categories: tuple[str, ...],
    *,
    skip_prefixes: tuple[str, ...] = SKIP_PREFIXES,
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for category in categories:
        for title in list_category_pages(category):
            if _should_skip(title, skip_prefixes) or title in seen:
                continue
            seen.add(title)
            result.append(title)
        time.sleep(0.15)
    return result


@register_parser
class OniParser(GameParser):
    game_id = "oni"

    def available_collections(self) -> list[str]:
        return list(COLLECTIONS.keys())

    def populate(self, ctx: PopulateContext) -> PopulateResult:
        result = PopulateResult()
        targets = ctx.collections or self.available_collections()
        delay = float(ctx.options.get("delay_sec", 0.35))
        batch_size = int(ctx.options.get("batch_size", 40))

        meta = load_json(ctx.game_dir / "meta.json") if (ctx.game_dir / "meta.json").exists() else {}
        meta.setdefault(
            "collections",
            {name: {"file": f"{name}.json"} for name in COLLECTIONS},
        )
        meta["wiki"] = "https://oxygennotincluded.wiki.gg"
        write_json(ctx.game_dir / "meta.json", meta)

        for collection in targets:
            if collection not in COLLECTIONS:
                result.errors.append(f"unknown collection: {collection}")
                continue
            self._populate_collection(ctx, collection, result, delay=delay, batch_size=batch_size)
        return result

    def _populate_collection(
        self,
        ctx: PopulateContext,
        collection: str,
        result: PopulateResult,
        *,
        delay: float,
        batch_size: int,
    ) -> None:
        spec = COLLECTIONS[collection]
        path = ctx.game_dir / f"{collection}.json"

        if spec.get("parse_mode") == "static":
            self._install_static_collection(ctx, collection, path, result)
            return

        existing = load_json(path)
        skip_prefixes = tuple(spec.get("skip_prefixes", SKIP_PREFIXES))
        titles = _unique_titles(tuple(spec["categories"]), skip_prefixes=skip_prefixes)
        if ctx.options.get("limit"):
            titles = titles[: int(ctx.options["limit"])]

        updated = 0
        processed = 0
        label = spec["label"]
        parse_mode = spec.get("parse_mode", "infobox")

        for i in range(0, len(titles), batch_size):
            batch = titles[i : i + batch_size]
            try:
                texts = fetch_wikitext_batch(batch)
            except Exception as exc:
                result.errors.append(f"{collection} batch {i}: {exc}")
                time.sleep(delay * 2)
                continue

            for title in batch:
                wikitext = texts.get(title, "")
                if parse_mode == "guide":
                    entry = parse_guide_page(title, wikitext)
                else:
                    entry = parse_page(title, wikitext, label)
                if not entry:
                    continue
                processed += 1
                new_data = entry_to_dict(entry)
                old = existing.get(entry.key, {})
                merged = {**new_data, **{k: v for k, v in old.items() if k == "note"}}
                if merged != old:
                    updated += 1
                existing[entry.key] = merged

            write_json(path, existing)
            time.sleep(delay)

        result.processed[collection] = processed
        result.updated[collection] = updated

    def _install_static_collection(
        self,
        ctx: PopulateContext,
        collection: str,
        path: Path,
        result: PopulateResult,
    ) -> None:
        if collection == "topics" and _BUNDLED_TOPICS.exists():
            data = load_json(_BUNDLED_TOPICS)
            write_json(path, data)
            result.processed[collection] = len(data)
            result.updated[collection] = len(data)
        elif path.exists():
            result.processed[collection] = len(load_json(path))
            result.updated[collection] = 0
        else:
            result.errors.append(f"{collection}: bundled source missing")
