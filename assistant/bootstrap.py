"""Логирование и сообщения об ошибках при запуске без консоли."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import BASE_DIR


def setup_logging() -> Path:
    log_dir = BASE_DIR / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "assistant.log"

    root = logging.getLogger()
    if root.handlers:
        return log_path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    return log_path


def show_fatal_error(title: str, message: str, log_path: Path | None = None) -> None:
    if log_path:
        message = f"{message}\n\nЛог: {log_path}"
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        if sys.stdout and sys.stdout.isatty():
            print(f"{title}: {message}", file=sys.stderr)
