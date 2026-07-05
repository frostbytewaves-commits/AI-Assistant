"""Запуск Game AI Assistant."""

import sys
import traceback

from assistant.bootstrap import setup_logging, show_fatal_error
from assistant.single_instance import acquire_single_instance


def _run() -> None:
    import logging

    logging.info("=== Game Assistant start ===")

    from assistant.main import main

    main()


if __name__ == "__main__":
    log_path = None
    try:
        log_path = setup_logging()
        if not acquire_single_instance():
            show_fatal_error(
                "Game Assistant",
                "Ассистент уже запущен.\n\nЗакрой предыдущее окно или заверши процесс в диспетчере задач.",
                log_path,
            )
            sys.exit(0)
        _run()
    except SystemExit:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            import logging

            logging.exception("Fatal startup error")
        except Exception:
            pass
        show_fatal_error("Game Assistant — ошибка запуска", f"{exc}\n\n{tb}", log_path)
        sys.exit(1)
