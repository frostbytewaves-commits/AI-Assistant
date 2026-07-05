╔══════════════════════════════════════════════════════════════╗
║  ВНИМАНИЕ: эта папка больше НЕ используется ассистентом!     ║
╚══════════════════════════════════════════════════════════════╝

Актуальная база Minecraft лежит здесь:

  C:\AI-Assistant-Data\games\minecraft\

Файлы (не папки!):
  blocks.json      — все блоки (~1166)
  recipes.json     — все рецепты (~886)
  mobs.json        — мобы и дроп
  versions.json    — версии игры
  version_changes.json — что добавилось в каждой версии

Проверить путь и размер файлов:
  python populate_game_db.py path

Обновить блоки и рецепты:
  python populate_game_db.py populate --game minecraft --collections versions,blocks,recipes --version 1.21.11 --play-version 1.21.11

Открыть в проводнике:
  explorer C:\AI-Assistant-Data\games\minecraft
