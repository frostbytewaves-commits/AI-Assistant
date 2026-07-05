"""Один экземпляр ассистента — без конфликтов hotkey и Ollama."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
_MUTEX_NAME = "Global\\GameAssistantSingleInstance"


def acquire_single_instance() -> bool:
    """True = можно запускаться, False = уже работает другой экземпляр."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    return True
