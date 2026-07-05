"""Загрузка и разбор страниц minecraft.wiki."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

WIKI_API = "https://minecraft.wiki/api.php"
USER_AGENT = "AI-Assistant-GameDBParser/1.0 (minecraft; local assistant)"


@dataclass
class DropEntry:
    item: str
    count: str
    note: str = ""


@dataclass
class MobWikiData:
    mob_id: str
    drops: list[DropEntry] = field(default_factory=list)
    xp: str = ""
    wiki_title: str = ""
    error: str = ""


def mob_id_to_wiki_title(mob_id: str) -> str:
    return " ".join(part.capitalize() for part in mob_id.split())


def _wiki_get(params: dict[str, str], timeout: int = 30) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    url = f"{WIKI_API}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_wikitext(page_title: str) -> str:
    data = _wiki_get({"action": "parse", "page": page_title, "prop": "wikitext"})
    return data["parse"]["wikitext"]["*"]


def _parse_drop_line(line: str) -> dict[str, str] | None:
    if "{{DropLine" not in line:
        return None
    params: dict[str, str] = {}
    for key, value in re.findall(r"(\w+)=([^|}]+)", line):
        params[key] = value.strip()
    return params if "name" in params else None


def _format_count(quantity: str, looting: str = "") -> str:
    quantity = quantity.strip().replace("-", "–")
    if not quantity:
        return "?"
    return quantity


def _note_from_params(params: dict[str, str]) -> str:
    notes: list[str] = []
    raw = params.get("notes", "")
    if raw in ("burn",):
        return "Только если убит огнём"
    if raw in ("not_burn",):
        return ""
    if raw == "wool":
        return "Цвет шерсти = цвет овцы; ножницы: 1–3 без убийства"
    if "player_or_pet" in raw:
        notes.append("Только если убит игроком/питомцем")
    if "charged_creeper" in raw:
        notes.append("Только заряженным крипером")
    if params.get("dropchance"):
        try:
            if float(params["dropchance"]) <= 0.05:
                notes.append("Редко")
        except ValueError:
            pass
    if params.get("edition") == "bedrock":
        notes.append("Bedrock")
    if raw and raw not in ("burn", "not_burn", "wool", "player_or_pet"):
        notes.append(raw.replace("_", " "))
    return "; ".join(notes)


def _should_skip_drop(params: dict[str, str]) -> bool:
    notes = params.get("notes", "")
    if params.get("edition") == "bedrock":
        return True
    if notes in ("burn",):
        return True
    if "charged_creeper" in notes:
        return True
    if "chicken_jockey" in notes or "zombie_horseman" in notes:
        return True
    name = params.get("name", "").lower()
    if name.startswith("music disc"):
        return True
    if "head" in name and "zombie" in name:
        return True
    return False


def parse_drops(wikitext: str) -> list[DropEntry]:
    block = ""
    for pattern in (
        r"=== On death ===\n\{\{DropTable\n(.*?)\n\}\}",
        r"== Drops ==\n\{\{DropTable\n(.*?)\n\}\}",
    ):
        match = re.search(pattern, wikitext, re.S)
        if match:
            block = match.group(1)
            break
    if not block:
        return []

    drops: list[DropEntry] = []
    seen: set[str] = set()
    for line in block.split("\n"):
        params = _parse_drop_line(line)
        if not params or _should_skip_drop(params):
            continue
        item = params["name"].lower().strip()
        if item in seen:
            continue
        seen.add(item)
        count = _format_count(
            params.get("quantity", "1" if params.get("notes") == "wool" else "?"),
        )
        drops.append(DropEntry(item=item, count=count, note=_note_from_params(params)))
    return drops


def parse_xp(wikitext: str) -> str:
    match = re.search(r"\{\{xp\|([^}|]+)(?:\|([^}|]+))?", wikitext)
    if not match:
        return ""
    low = match.group(1).strip()
    high = match.group(2).strip() if match.group(2) else ""
    return f"{low}–{high}" if high and high != low else low


def fetch_mob(mob_id: str, *, delay_sec: float = 0.35) -> MobWikiData:
    title = mob_id_to_wiki_title(mob_id)
    result = MobWikiData(mob_id=mob_id, wiki_title=title)
    try:
        wikitext = fetch_wikitext(title)
        result.drops = parse_drops(wikitext)
        result.xp = parse_xp(wikitext)
    except urllib.error.HTTPError as exc:
        result.error = f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        result.error = str(exc.reason)
    except KeyError:
        result.error = "Страница не найдена"
    except json.JSONDecodeError:
        result.error = "Некорректный ответ API"
    time.sleep(delay_sec)
    return result


def fetch_mobs(mob_ids: list[str], *, delay_sec: float = 0.35) -> list[MobWikiData]:
    return [fetch_mob(mob_id, delay_sec=delay_sec) for mob_id in mob_ids]
