"""CLI универсального парсера баз данных игр."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from game_data.paths import (
    DEFAULT_DATA_ROOT,
    ensure_data_layout,
    migrate_legacy_games,
    resolve_data_root,
    resolve_games_dir,
)
from game_data.schema import load_registry

from .core.base import PopulateContext
from .core.registry import get_parser, list_parsers


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def cmd_path(args: argparse.Namespace) -> int:
    games_dir = Path(args.games_dir).expanduser() if args.games_dir else resolve_games_dir()
    data_root = resolve_data_root()
    mc = games_dir / "minecraft"
    print(f"Корень данных:  {data_root}")
    print(f"База игр:       {games_dir}")
    print(f"Minecraft:      {mc}")
    print()
    if not mc.exists():
        print("Папка minecraft не найдена. Запустите:")
        print("  python populate_game_db.py init --migrate")
        print("  python populate_game_db.py populate --game minecraft --collections versions,blocks,recipes")
        return 1
    print("Файлы (блоки = blocks.json, не отдельная папка):")
    for f in sorted(mc.glob("*.json")):
        kb = f.stat().st_size // 1024
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            n = len(data) if isinstance(data, dict) else "?"
        except Exception:
            n = "?"
        print(f"  {f.name:24} {kb:5} KB   записей: {n}")
    print()
    print("Старая папка C:\\AI-Assistant\\data\\games — НЕ используется ассистентом.")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    data_root = Path(args.data_dir).expanduser() if args.data_dir else resolve_data_root()
    games_dir = ensure_data_layout(data_root)
    copied: list[str] = []
    if args.migrate:
        copied = migrate_legacy_games(games_dir)
    print(f"Корень данных: {data_root}")
    print(f"База игр:      {games_dir}")
    if copied:
        print(f"Мигрировано:   {', '.join(copied)}")
    else:
        print("Миграция:      нечего копировать (или уже перенесено)")
    print("\nПодсказка: укажите путь в local_config.json или переменной AI_ASSISTANT_DATA_DIR")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    games_dir = Path(args.games_dir).expanduser() if args.games_dir else resolve_games_dir()
    registry = load_registry(games_dir)
    parsers = {p.game_id: p for p in list_parsers()}

    print(f"Папка базы: {games_dir}\n")
    if not registry:
        print("registry.json пуст или отсутствует. Запустите: populate_game_db.py init --migrate")
        return 1

    for gid, entry in registry.items():
        parser = parsers.get(entry.parser or gid)
        collections = entry.collections or ({"*": "?"} if parser else {})
        parser_note = parser.describe() if parser else "парсер не подключён (ручное заполнение JSON)"
        default = " [default]" if entry.default else ""
        print(f"- {gid}{default}: {entry.name_ru}")
        print(f"    parser: {entry.parser or '—'}")
        print(f"    collections: {', '.join(collections.keys())}")
        print(f"    {parser_note}")
    return 0


def cmd_populate(args: argparse.Namespace) -> int:
    games_dir = Path(args.games_dir).expanduser() if args.games_dir else resolve_games_dir()
    registry = load_registry(games_dir)
    game_id = args.game

    entry = registry.get(game_id)
    if not entry:
        print(f"Игра «{game_id}» не найдена в {games_dir / 'registry.json'}")
        return 1

    parser_id = entry.parser or game_id
    parser = get_parser(parser_id)
    if not parser:
        print(f"Парсер «{parser_id}» не реализован. Добавьте модуль в tools/game_db_parser/games/")
        return 1

    game_dir = games_dir / game_id
    game_dir.mkdir(parents=True, exist_ok=True)

    collections = [c.strip() for c in args.collections.split(",") if c.strip()] if args.collections else parser.available_collections()
    options = {
        "version": args.version,
        "delay_sec": args.delay,
        "play_version": args.play_version,
        "full_recipes": not args.priority_recipes,
        "wiki_versions": not args.no_wiki and not args.offline,
        "offline": args.offline,
    }
    if args.limit:
        options["limit"] = args.limit
    if args.mob:
        options["mob_filter"] = args.mob

    print(f"Игра: {entry.name_ru} ({game_id})")
    print(f"Коллекции: {', '.join(collections)}")
    if game_id == "minecraft":
        print(f"Версия data: {args.version}, версия игрока: {args.play_version}")
    print(f"Папка: {game_dir}\n")

    ctx = PopulateContext(
        game_id=game_id,
        game_dir=game_dir,
        games_dir=games_dir,
        collections=collections,
        only_missing=args.only_missing,
        options=options,
    )
    result = parser.populate(ctx)

    for name, count in result.processed.items():
        print(f"  {name}: обработано {count}, обновлено {result.updated.get(name, 0)}")
    for err in result.errors:
        print(f"  ! {err}")

    print(f"\nГотово: {game_dir}")
    return 0 if result.ok else 1


def cmd_add_game(args: argparse.Namespace) -> int:
    games_dir = Path(args.games_dir).expanduser() if args.games_dir else resolve_games_dir()
    ensure_data_layout(games_dir.parent if games_dir.name == "games" else resolve_data_root())

    game_id = args.game_id.strip().lower().replace(" ", "_")
    if not game_id.isidentifier():
        print("game_id должен быть латиницей: my_game, valorant, etc.")
        return 1

    registry_path = games_dir / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    if game_id in registry:
        print(f"Игра «{game_id}» уже есть в registry.json")
        return 1

    collections = {}
    for spec in (args.collection or ["entities:entities.json"]):
        if ":" in spec:
            cname, fname = spec.split(":", 1)
        else:
            cname, fname = spec, f"{spec}.json"
        collections[cname.strip()] = fname.strip()

    registry[game_id] = {
        "id": game_id,
        "name": args.name or game_id.title(),
        "name_ru": args.name_ru or args.name or game_id.title(),
        "version_note": args.version_note or "",
        "default": False,
        "parser": args.parser,
        "collections": collections,
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    game_dir = games_dir / game_id
    game_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "parser": args.parser,
        "collections": {
            name: {"file": fname, "description_ru": f"Коллекция {name}"}
            for name, fname in collections.items()
        },
    }
    (game_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for fname in collections.values():
        path = game_dir / fname
        if not path.exists():
            path.write_text("{}\n", encoding="utf-8")

    template_dir = Path(__file__).parent / "games" / "_template"
    parser_example = template_dir / "parser.py.example"
    if parser_example.exists() and args.parser:
        dst = Path(__file__).parent / "games" / args.parser / "parser.py"
        if not dst.exists():
            text = parser_example.read_text(encoding="utf-8").replace("GAME_ID", args.parser)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
            print(f"Шаблон парсера: {dst}")

    print(f"Создана игра: {game_id}")
    print(f"  registry: {registry_path}")
    print(f"  data:     {game_dir}")
    if not args.parser:
        print("  parser:   null — заполняйте JSON вручную или добавьте парсер позже")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()

    parser = argparse.ArgumentParser(
        description="Универсальный парсер баз данных игр для AI-Assistant.",
    )
    parser.add_argument(
        "--games-dir",
        type=Path,
        default=None,
        help=f"Папка games (по умолчанию: {DEFAULT_DATA_ROOT}\\games или из local_config.json)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Создать внешнюю папку данных")
    init_p.add_argument("--data-dir", type=Path, default=None, help="Корень данных (по умолчанию C:\\AI-Assistant-Data)")
    init_p.add_argument("--migrate", action="store_true", help="Скопировать data/games из папки ассистента")
    init_p.set_defaults(func=cmd_init)

    path_p = sub.add_parser("path", help="Показать, где лежит база данных")
    path_p.set_defaults(func=cmd_path)

    list_p = sub.add_parser("list", help="Список игр и парсеров")
    list_p.set_defaults(func=cmd_list)

    pop_p = sub.add_parser("populate", help="Заполнить базу для игры")
    pop_p.add_argument("--game", required=True, help="ID игры из registry.json (minecraft, …)")
    pop_p.add_argument(
        "--collections",
        default="",
        help="Коллекции: mobs,recipes,blocks,versions",
    )
    pop_p.add_argument("--only-missing", action="store_true")
    pop_p.add_argument("--version", default="1.21.11", help="[minecraft] версия minecraft-data для рецептов/блоков")
    pop_p.add_argument(
        "--play-version",
        default="1.21.11",
        help="[minecraft] ваша версия игры (фильтр added_in/removed_in)",
    )
    pop_p.add_argument(
        "--priority-recipes",
        action="store_true",
        help="[minecraft] только базовые рецепты (быстро), без полного каталога",
    )
    pop_p.add_argument("--no-wiki", action="store_true", help="[minecraft] не подгружать 26.x с wiki")
    pop_p.add_argument(
        "--offline",
        action="store_true",
        help="[minecraft] без wiki; только minecraft-data для --version",
    )
    pop_p.add_argument("--delay", type=float, default=0.35, help="[minecraft/oni] пауза между запросами wiki (сек)")
    pop_p.add_argument("--limit", type=int, default=0, help="[oni] лимит страниц на коллекцию (0 = все)")
    pop_p.add_argument("--mob", action="append", dest="mob", metavar="ID")
    pop_p.set_defaults(func=cmd_populate)

    add_p = sub.add_parser("add-game", help="Добавить новую игру в registry")
    add_p.add_argument("game_id", help="ID: valorant, witcher3, …")
    add_p.add_argument("--name", default="", help="Название EN")
    add_p.add_argument("--name-ru", default="", dest="name_ru")
    add_p.add_argument("--version-note", default="")
    add_p.add_argument("--parser", default=None, help="ID парсера (папка tools/game_db_parser/games/<parser>/)")
    add_p.add_argument(
        "--collection",
        action="append",
        help="Коллекция: entities:entities.json (можно несколько раз)",
    )
    add_p.set_defaults(func=cmd_add_game)

    args = parser.parse_args(argv)
    return args.func(args)
