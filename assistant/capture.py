import ctypes
import time
from pathlib import Path

from PIL import ImageGrab

user32 = ctypes.windll.user32


def get_foreground_window_handle() -> int:
    return int(user32.GetForegroundWindow() or 0)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def get_foreground_window_rect(excluded_hwnd: int | None = None) -> tuple[int, int, int, int]:
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        raise RuntimeError("Не удалось получить активное окно")
    if excluded_hwnd and hwnd == excluded_hwnd:
        raise RuntimeError("Активно окно ассистента, а не игра")

    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Не удалось получить координаты окна")
    if rect.right <= rect.left or rect.bottom <= rect.top:
        raise RuntimeError("Некорректные координаты окна")

    return rect.left, rect.top, rect.right, rect.bottom


def get_foreground_window_title(excluded_hwnd: int | None = None) -> str:
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        return ""
    if excluded_hwnd and hwnd == excluded_hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip()


def get_foreground_process_name(excluded_hwnd: int | None = None) -> str:
    """Executable name of the foreground window process (best-effort)."""
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        return ""
    if excluded_hwnd and hwnd == excluded_hwnd:
        return ""
    return get_process_name_for_hwnd(int(hwnd))


def get_process_name_for_hwnd(hwnd: int) -> str:
    """Executable name for a window handle (best-effort, never blocks long)."""
    if not hwnd:
        return ""
    try:
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(260)
            buf = ctypes.create_unicode_buffer(260)
            QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
            if not QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return ""
            path = buf.value.strip()
            if not path:
                return ""
            return Path(path).name
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def _window_title(hwnd: int) -> str:
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        # Strip bidi marks that break console/logs; keep the rest of the title.
        return buf.value.strip().replace("\u200e", "").replace("\u200f", "")
    except Exception:
        return ""


_SKIP_WINDOW_TITLES = {
    "",
    "program manager",
    "default ime",
    "msctfime ui",
    "windows input experience",
}


def list_visible_windows(
    excluded_hwnd: int | None = None,
    *,
    limit: int = 18,
) -> list[dict[str, str | int]]:
    """Top-level visible windows with a title (Win32 EnumWindows).

    Each item: hwnd, title, process_name. Foreground first when present.
    Process names are resolved only for the final limited set (faster / safer).
    """
    GW_OWNER = 4
    raw: list[tuple[int, str]] = []
    seen_titles: set[str] = set()
    hard_cap = max(limit * 4, limit)

    def _callback(hwnd, _lparam):  # noqa: ANN001
        if len(raw) >= hard_cap:
            return False
        try:
            hwnd_i = int(hwnd)
            if excluded_hwnd and hwnd_i == int(excluded_hwnd):
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindow(hwnd, GW_OWNER):
                return True
            title = _window_title(hwnd_i)
            low = title.lower()
            if low in _SKIP_WINDOW_TITLES or low in seen_titles:
                return True
            seen_titles.add(low)
            raw.append((hwnd_i, title))
        except Exception:
            return True
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_callback)
    list_visible_windows._enum_proc = enum_proc  # type: ignore[attr-defined]
    try:
        user32.EnumWindows(enum_proc, 0)
    except Exception:
        return []

    fg = get_foreground_window_handle()
    if fg and (not excluded_hwnd or fg != int(excluded_hwnd)):
        raw.sort(key=lambda item: 0 if item[0] == fg else 1)

    entries: list[dict[str, str | int]] = []
    for hwnd_i, title in raw[: max(1, limit)]:
        entries.append(
            {
                "hwnd": hwnd_i,
                "title": title,
                "process_name": get_process_name_for_hwnd(hwnd_i),
            }
        )
    return entries


def is_minecraft_window_title(title: str) -> bool:
    if not title:
        return False
    lower = title.lower()
    markers = (
        "minecraft",
        "lunar client",
        "badlion client",
        "feather client",
        "labymod",
        "forge",
        "fabric",
    )
    return any(marker in lower for marker in markers)


def is_oni_window_title(title: str) -> bool:
    if not title:
        return False
    lower = title.lower()
    return "oxygen not included" in lower or lower.startswith("oni ")


def capture_foreground_window(
    screenshot_dir: Path,
    excluded_hwnd: int | None = None,
    prefix: str = "game",
) -> Path:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    image_path = screenshot_dir / f"{prefix}-{timestamp}.png"
    left, top, right, bottom = get_foreground_window_rect(excluded_hwnd=excluded_hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    image.save(image_path)
    return image_path


def capture_full_screen(screenshot_dir: Path, prefix: str = "screen") -> Path:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    image_path = screenshot_dir / f"{prefix}-{timestamp}.png"
    image = ImageGrab.grab(all_screens=True)
    image.save(image_path)
    return image_path
