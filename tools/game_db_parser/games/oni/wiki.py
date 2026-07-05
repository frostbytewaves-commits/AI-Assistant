"""Парсинг oxygennotincluded.wiki.gg."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

WIKI_API = "https://oxygennotincluded.wiki.gg/api.php"
USER_AGENT = "AI-Assistant-ONI-Parser/1.0 (local game assistant)"

INFOBOX_PREFIXES = (
    "Infobox Building",
    "Infobox Element",
    "Infobox Creature",
    "InfoboxStructure",
    "Infobox Food",
    "InfoboxGerm",
    "Infobox Plant",
    "Infobox Biome",
    "Infobox Tech",
)


@dataclass
class OniEntry:
    key: str
    name: str
    kind: str
    description: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    summary: str = ""


def title_to_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def _wiki_get(params: dict[str, str], *, retries: int = 4) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    url = f"{WIKI_API}?{query}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    assert last_err is not None
    raise last_err


def list_category_pages(category: str) -> list[str]:
    titles: list[str] = []
    continue_token: str | None = None
    while True:
        params: dict[str, str] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
        }
        if continue_token:
            params["cmcontinue"] = continue_token
        data = _wiki_get(params)
        for member in data.get("query", {}).get("categorymembers", []):
            if member.get("ns") != 0:
                continue
            titles.append(member["title"])
        cont = data.get("continue", {})
        continue_token = cont.get("cmcontinue")
        if not continue_token:
            break
        time.sleep(0.2)
    return titles


def fetch_wikitext_batch(titles: list[str]) -> dict[str, str]:
    if not titles:
        return {}
    joined = "|".join(titles)
    data = _wiki_get(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "titles": joined,
        }
    )
    pages = data.get("query", {}).get("pages", {})
    result: dict[str, str] = {}
    for page in pages.values():
        title = page.get("title", "")
        revs = page.get("revisions", [])
        if title and revs:
            result[title] = revs[0].get("*", "")
    return result


def _clean_wiki_text(text: str) -> str:
    text = re.sub(r"\{\{[^}]+\}\}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = text.replace("<br>", " ").replace("<br/>", " ")
    return re.sub(r"\s+", " ", text).strip()


def _detect_infobox_kind(wikitext: str) -> str:
    for prefix in INFOBOX_PREFIXES:
        if prefix.lower().replace(" ", "") in wikitext.lower().replace(" ", "")[:500]:
            return prefix.replace("Infobox ", "").replace("Infobox", "").strip() or "Entry"
    if "{{InfoboxStructure" in wikitext:
        return "Geyser"
    if "{{InfoboxGerm" in wikitext:
        return "Disease"
    return "Entry"


def parse_infobox_fields(wikitext: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_box = False
    for line in wikitext.splitlines():
        stripped = line.strip()
        if stripped.startswith("{{Infobox") or stripped.startswith("{{InfoboxStructure"):
            in_box = True
            continue
        if in_box and stripped == "}}":
            break
        if not in_box or not stripped.startswith("|"):
            continue
        match = re.match(r"\|\s*([\w]+)\s*=\s*(.*)", stripped)
        if match:
            key, val = match.group(1), _clean_wiki_text(match.group(2))
            if val:
                fields[key] = val
    return fields


def extract_summary(wikitext: str) -> str:
    for line in wikitext.splitlines():
        if line.startswith("{{") or line.startswith("|") or not line.strip():
            continue
        if line.strip().startswith("=="):
            break
        cleaned = _clean_wiki_text(line)
        if len(cleaned) > 40:
            return cleaned[:600]
    return ""


def extract_sections(wikitext: str) -> list[tuple[str, str]]:
    """Extract wiki section headers and body text."""
    sections: list[tuple[str, str]] = []
    current_header = "Overview"
    current_lines: list[str] = []
    for line in wikitext.splitlines():
        stripped = line.strip()
        if stripped.startswith("==") and not stripped.startswith("==="):
            if current_lines:
                body = _clean_wiki_text("\n".join(current_lines))
                if len(body) > 30:
                    sections.append((current_header, body[:2000]))
            current_header = _clean_wiki_text(stripped.strip("= "))
            current_lines = []
            continue
        if stripped.startswith("{{") or stripped == "}}" or stripped.startswith("|"):
            continue
        if stripped.startswith("[[Category:"):
            continue
        current_lines.append(line)
    if current_lines:
        body = _clean_wiki_text("\n".join(current_lines))
        if len(body) > 30:
            sections.append((current_header, body[:2000]))
    return sections


def parse_guide_page(title: str, wikitext: str) -> OniEntry | None:
    if not wikitext or len(wikitext) < 80:
        return None
    sections = extract_sections(wikitext)
    if not sections:
        summary = extract_summary(wikitext)
        if len(summary) < 50:
            return None
        sections = [("Overview", summary)]
    body_parts = []
    for header, text in sections[:12]:
        body_parts.append(f"**{header}:** {text}")
    body = "\n\n".join(body_parts)
    if len(body) < 60:
        return None
    tags = [t.lower() for t in re.findall(r"[a-zA-Z]{4,}", title)]
    tags += [t.lower() for t in re.findall(r"[a-zA-Z]{4,}", body[:500])]
    return OniEntry(
        key=title_to_key(title),
        name=title.replace("Guide/", ""),
        kind="Guide",
        description=body[:5000],
        summary=sections[0][1][:400] if sections else "",
        fields={"tags": ", ".join(sorted(set(tags))[:20])},
    )


def parse_page(title: str, wikitext: str, default_kind: str) -> OniEntry | None:
    if not wikitext or len(wikitext) < 30:
        return None
    fields = parse_infobox_fields(wikitext)
    kind = _detect_infobox_kind(wikitext)
    if kind == "Entry" and not fields and not extract_summary(wikitext):
        return None

    description = (
        fields.get("description")
        or fields.get("desc")
        or fields.get("tooltip")
        or fields.get("name")
        or extract_summary(wikitext)
    )
    return OniEntry(
        key=title_to_key(title),
        name=fields.get("displaytitle") or fields.get("name") or title,
        kind=default_kind if default_kind != "Entry" else kind,
        description=description[:800],
        fields={k: v for k, v in fields.items() if k not in ("displaytitle", "name")},
        summary=extract_summary(wikitext)[:800],
    )


def entry_to_dict(entry: OniEntry) -> dict:
    data: dict = {
        "name": entry.name,
        "kind": entry.kind,
    }
    if entry.description:
        data["description"] = entry.description
    if entry.summary and entry.summary != entry.description:
        data["summary"] = entry.summary
    for key, val in entry.fields.items():
        if key in ("description", "desc", "tooltip"):
            continue
        data[key] = val
    return data
