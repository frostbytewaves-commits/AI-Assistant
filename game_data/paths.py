"""Пути к внешней базе данных игр (вне папки ассистента)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

try:
    from assistant.runtime_paths import app_root
except Exception:  # pragma: no cover — early import / tools
    def app_root() -> Path:  # type: ignore[misc]
        return Path(__file__).resolve().parents[1]


PROJECT_ROOT = app_root()
DEFAULT_DATA_ROOT = Path(r"C:\AI-Assistant-Data")
LEGACY_GAMES_DIR = PROJECT_ROOT / "data" / "games"
LOCAL_CONFIG = PROJECT_ROOT / "local_config.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


_local = _read_json(LOCAL_CONFIG)
DEFAULT_MINECRAFT_PLAY_VERSION = str(_local.get("minecraft_play_version", ""))


def resolve_data_root() -> Path:
    env = os.environ.get("AI_ASSISTANT_DATA_DIR")
    if env:
        return Path(env).expanduser()

    local = _read_json(LOCAL_CONFIG)
    if local.get("data_root"):
        return Path(local["data_root"]).expanduser()

    external = DEFAULT_DATA_ROOT / "config.json"
    if external.exists():
        cfg = _read_json(external)
        if cfg.get("data_root"):
            return Path(cfg["data_root"]).expanduser()

    return DEFAULT_DATA_ROOT


def resolve_games_dir() -> Path:
    env = os.environ.get("AI_ASSISTANT_GAMES_DIR")
    if env:
        return Path(env).expanduser()

    local = _read_json(LOCAL_CONFIG)
    if local.get("games_data_dir"):
        return Path(local["games_data_dir"]).expanduser()

    external = resolve_data_root() / "config.json"
    if external.exists():
        cfg = _read_json(external)
        if cfg.get("games_dir"):
            return Path(cfg["games_dir"]).expanduser()

    return resolve_data_root() / "games"


def ensure_data_layout(data_root: Path | None = None) -> Path:
    root = data_root or resolve_data_root()
    games_dir = root / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    config_path = root / "config.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps(
                {
                    "data_root": str(root),
                    "games_dir": str(games_dir),
                    "comment": "База знаний игр для AI-Assistant. Можно менять путь.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    registry_path = games_dir / "registry.json"
    if not registry_path.exists():
        registry_path.write_text(
            json.dumps(_default_registry(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return games_dir


def _default_registry() -> dict:
    return {
        "minecraft": {
            "id": "minecraft",
            "name": "Minecraft Java/Bedrock",
            "name_ru": "Minecraft",
            "version_note": "Vanilla Java 1.20+",
            "default": False,
            "parser": "minecraft",
            "collections": {
                "mobs": "mobs.json",
                "recipes": "recipes.json",
                "blocks": "blocks.json",
                "versions": "versions.json",
            },
        },
        "oni": {
            "id": "oni",
            "name": "Oxygen Not Included",
            "name_ru": "Oxygen Not Included",
            "version_note": "ONI wiki database",
            "default": True,
            "parser": "oni",
            "collections": {
                "buildings": "buildings.json",
                "elements": "elements.json",
                "critters": "critters.json",
                "geysers": "geysers.json",
                "food": "food.json",
                "diseases": "diseases.json",
                "biomes": "biomes.json",
                "research": "research.json",
                "plants": "plants.json",
                "guides": "guides.json",
                "topics": "topics.json",
            },
        },
    }


def migrate_legacy_games(games_dir: Path, *, legacy_dir: Path | None = None) -> list[str]:
    """Копирует data/games из проекта во внешнюю папку, если там ещё пусто."""
    legacy = legacy_dir or LEGACY_GAMES_DIR
    copied: list[str] = []
    if not legacy.exists():
        return copied

    games_dir.mkdir(parents=True, exist_ok=True)

    registry_dst = games_dir / "registry.json"
    if not registry_dst.exists() and (legacy / "registry.json").exists():
        shutil.copy2(legacy / "registry.json", registry_dst)
        copied.append("registry.json")

    for game_dir in legacy.iterdir():
        if not game_dir.is_dir():
            continue
        dst = games_dir / game_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        for json_file in game_dir.glob("*.json"):
            target = dst / json_file.name
            if not target.exists():
                shutil.copy2(json_file, target)
                copied.append(f"{game_dir.name}/{json_file.name}")

    return copied
