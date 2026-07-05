#!/usr/bin/env python3
"""Заполнение базы данных игр (универсальный парсер).

Примеры:
  python populate_game_db.py init --migrate
  python populate_game_db.py list
  python populate_game_db.py populate --game minecraft
  python populate_game_db.py add-game valorant --name-ru Valorant --collection agents:agents.json
"""

from tools.game_db_parser.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
