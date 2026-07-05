from tools.game_db_parser.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["populate", "--game", "minecraft"] + __import__("sys").argv[1:]))
