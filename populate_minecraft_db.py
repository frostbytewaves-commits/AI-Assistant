#!/usr/bin/env python3
"""Обратная совместимость → populate_game_db.py populate --game minecraft."""

from __future__ import annotations

import sys

from tools.game_db_parser.cli import main as cli_main

_MINECRAFT_FLAGS = {
    "--mobs-only": ["--collections", "mobs"],
    "--recipes-only": ["--collections", "recipes"],
    "--only-missing": ["--only-missing"],
}


def main() -> int:
    argv = ["populate", "--game", "minecraft"]
    skip_next = False
    for i, arg in enumerate(sys.argv[1:], start=1):
        if skip_next:
            skip_next = False
            continue
        if arg in _MINECRAFT_FLAGS:
            argv.extend(_MINECRAFT_FLAGS[arg])
            continue
        if arg in ("--mob", "--games-dir", "--version", "--delay") and i < len(sys.argv) - 1:
            argv.extend([arg, sys.argv[i + 1]])
            skip_next = True
            continue
        if arg.startswith(("--games-dir=", "--version=", "--delay=")):
            argv.append(arg)
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
