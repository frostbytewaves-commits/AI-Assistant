"""Точка входа игрового AI-ассистента."""

import logging

from .bootstrap import setup_logging
from .config import AssistantConfig, MODEL_PROFILE
from .overlay import GameAssistantApp

log = logging.getLogger(__name__)


def register_hotkeys(app: GameAssistantApp) -> bool:
    """Win32 hotkey без UAC; fallback на keyboard (нужен admin)."""
    cfg = app.config

    try:
        from .hotkeys import register_win_hotkeys

        hk = register_win_hotkeys(app)
        if hk._ready:
            return True
    except Exception as exc:
        log.warning("Win32 hotkeys failed: %s", exc)

    try:
        import keyboard
    except ImportError:
        log.warning("keyboard not installed — only UI buttons")
        return False

    def on_main_thread(callback) -> callable:
        def wrapper(*args, **kwargs):
            app.root.after(0, lambda: callback(*args, **kwargs))

        return wrapper

    try:
        keyboard.add_hotkey(
            cfg.hotkey_screen,
            on_main_thread(app.start_screen_analysis),
            suppress=False,
        )
        keyboard.add_hotkey(
            cfg.hotkey_toggle_speak,
            on_main_thread(app.toggle_speak),
            suppress=False,
        )
        keyboard.on_press_key(
            cfg.hotkey_voice,
            lambda _: app.root.after(0, app.start_voice_hold),
            suppress=False,
        )
        keyboard.on_release_key(
            cfg.hotkey_voice,
            lambda _: app.root.after(0, app.stop_voice_hold),
            suppress=False,
        )
        log.info("keyboard library hotkeys OK (may need admin)")
        return True
    except Exception as exc:
        log.warning("keyboard hotkeys failed: %s", exc)
        return False


def main() -> None:
    setup_logging()
    config = AssistantConfig()
    app = GameAssistantApp(config)
    hotkeys_ok = register_hotkeys(app)

    text = app.llm.resolve_text_model()
    vision = app.llm.resolve_vision_model()

    log.info("Game AI Assistant v2")
    log.info("Hotkey: %s", "OK" if hotkeys_ok else "NO")
    log.info(
        "Profile: %s | Text: %s | Vision: %s | Thinking: %s",
        MODEL_PROFILE,
        text,
        vision or "none",
        "on" if config.enable_thinking else "off",
    )

    if not hotkeys_ok:
        app.status_var.set("F8/F9/F10 unavailable — use window buttons")

    try:
        app.run()
    finally:
        hk = getattr(app, "_win_hotkeys", None)
        if hk is not None:
            hk.clear()
        else:
            try:
                import keyboard

                keyboard.clear_all_hotkeys()
            except Exception:
                pass
        log.info("=== Game Assistant stop ===")
