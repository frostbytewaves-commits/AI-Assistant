"""Глобальные hotkey через Win32 RegisterHotKey — без UAC."""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import time
from ctypes import wintypes
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .overlay import GameAssistantApp

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_DESTROY = 0x0002
MOD_NOREPEAT = 0x4000
HWND_MESSAGE = -3
ERROR_CLASS_ALREADY_EXISTS = 1410

VK_KEYS = {f"f{i}": 0x70 + i - 1 for i in range(1, 25)}

ID_SCREEN = 1
ID_SPEAK = 2
ID_VOICE = 3

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

_DEF_WNDPROC = WNDPROC(
    lambda hwnd, msg, wp, lp: user32.DefWindowProcW(hwnd, msg, wp, lp)
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _win_error(prefix: str) -> OSError:
    return OSError(f"{prefix} (win32 {ctypes.get_last_error()})")


def _register_wndclass(class_name: str) -> None:
    wc = WNDCLASSW()
    wc.lpfnWndProc = _DEF_WNDPROC
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = class_name
    atom = user32.RegisterClassW(ctypes.byref(wc))
    if atom:
        return
    err = ctypes.get_last_error()
    if err != ERROR_CLASS_ALREADY_EXISTS:
        raise _win_error(f"RegisterClassW failed for {class_name}")


def _create_message_window(class_name: str) -> int:
    _register_wndclass(class_name)
    for attempt in range(3):
        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            f"GameAssistantHotkeys-{os.getpid()}",
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            0,
            kernel32.GetModuleHandleW(None),
            None,
        )
        if hwnd:
            return int(hwnd)
        err = ctypes.get_last_error()
        log.warning("CreateWindowExW attempt %s failed: %s", attempt + 1, err)
        time.sleep(0.15 * (attempt + 1))
    raise _win_error("CreateWindowExW failed")


class WinHotkeys:
    def __init__(self, app: GameAssistantApp) -> None:
        self.app = app
        self._class_name = f"GameAssistantHotkeyWnd_{os.getpid()}"
        self._msg_hwnd: int = 0
        self._voice_vk: int | None = None
        self._polling_voice = False
        self._registered: list[int] = []
        self._stop = threading.Event()
        self._started = threading.Event()
        self._thread: threading.Thread | None = None
        self._ready = False
        self._activating = False
        self._keys: tuple[str, str, str] = ("f8", "f9", "f10")
        self._queue: queue.SimpleQueue[int] = queue.SimpleQueue()

    def _vk(self, name: str) -> int:
        key = name.lower().strip()
        if key not in VK_KEYS:
            raise ValueError(f"Unsupported hotkey: {name}")
        return VK_KEYS[key]

    def activate(self, screen: str, voice: str, speak: str) -> None:
        if self._ready or self._activating:
            return
        self._activating = True
        try:
            self._keys = (screen, voice, speak)
            self._voice_vk = self._vk(voice)
            self._stop.clear()
            self._started.clear()
            self._thread = threading.Thread(target=self._message_loop, name="WinHotkeys", daemon=True)
            self._thread.start()
            if not self._started.wait(timeout=5.0):
                raise OSError("Hotkey thread timeout")
            if not self._ready:
                raise OSError("Hotkey thread failed to register keys")
            self.app.root.after(50, self._poll_voice)
            self.app.root.after(50, self._drain_queue)
        finally:
            self._activating = False

    def _drain_queue(self) -> None:
        while True:
            try:
                hotkey_id = self._queue.get_nowait()
            except queue.Empty:
                break
            self._dispatch(hotkey_id)
        if not self._stop.is_set():
            self.app.root.after(50, self._drain_queue)

    def _message_loop(self) -> None:
        try:
            self._msg_hwnd = _create_message_window(self._class_name)
            screen, voice, speak = self._keys
            self._register(ID_SCREEN, screen)
            self._register(ID_SPEAK, speak)
            self._register(ID_VOICE, voice)
            self._ready = True
            self._started.set()
            log.info(
                "Win32 hotkeys OK: %s / %s / %s (hwnd=%s)",
                screen,
                voice,
                speak,
                self._msg_hwnd,
            )

            msg = wintypes.MSG()
            while not self._stop.is_set():
                ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if ret <= 0:
                    break
                if msg.message == WM_HOTKEY:
                    self._queue.put(int(msg.wParam))
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            log.error("Hotkey thread failed: %s", exc)
            self._ready = False
            self._started.set()
        finally:
            for hotkey_id in list(self._registered):
                try:
                    user32.UnregisterHotKey(self._msg_hwnd, hotkey_id)
                except Exception:
                    pass
            self._registered.clear()
            if self._msg_hwnd:
                user32.DestroyWindow(self._msg_hwnd)
                self._msg_hwnd = 0

    def _register(self, hotkey_id: int, key: str) -> None:
        vk = self._vk(key)
        ok = user32.RegisterHotKey(self._msg_hwnd, hotkey_id, MOD_NOREPEAT, vk)
        if not ok:
            raise _win_error(f"RegisterHotKey failed for {key}")
        self._registered.append(hotkey_id)

    def _poll_voice(self) -> None:
        if self._polling_voice:
            self._check_voice_release()
        if not self._stop.is_set():
            self.app.root.after(50, self._poll_voice)

    def _dispatch(self, hotkey_id: int) -> None:
        if hotkey_id == ID_SCREEN:
            self.app.start_screen_analysis()
        elif hotkey_id == ID_SPEAK:
            self.app.toggle_speak()
        elif hotkey_id == ID_VOICE:
            if self.app.voice_recording:
                self.app.stop_voice_hold()
            else:
                self._start_voice_with_poll()

    def _start_voice_with_poll(self) -> None:
        self.app.start_voice_hold()
        if self.app.voice_recording:
            self._polling_voice = True

    def _check_voice_release(self) -> None:
        if not self.app.voice_recording:
            self._polling_voice = False
            return
        if self._voice_vk is None:
            return
        if user32.GetAsyncKeyState(self._voice_vk) & 0x8000:
            return
        self._polling_voice = False
        self.app.stop_voice_hold()

    def clear(self) -> None:
        self._stop.set()
        if self._msg_hwnd:
            user32.PostMessageW(self._msg_hwnd, WM_DESTROY, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._ready = False


def register_win_hotkeys(app: GameAssistantApp) -> WinHotkeys:
    cfg = app.config
    hk = WinHotkeys(app)
    app._win_hotkeys = hk
    hk.activate(cfg.hotkey_screen, cfg.hotkey_voice, cfg.hotkey_toggle_speak)
    return hk
