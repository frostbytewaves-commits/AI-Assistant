"""Match user queries to open windows — aliases are app identity, not language routing."""

from __future__ import annotations

from typing import Any

from assistant.capture import list_visible_windows

# Everyday labels → substrings that identify real apps (title/process).
QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "vpn": (
        "hiddify",
        "clash",
        "v2rayn",
        "v2ray",
        "wireguard",
        "openvpn",
        "nordvpn",
        "mullvad",
        "protonvpn",
        "proton vpn",
        "warp",
        "sing-box",
        "nekoray",
        "shadowsocks",
    ),
    "впн": (
        "hiddify",
        "clash",
        "v2rayn",
        "v2ray",
        "wireguard",
        "openvpn",
        "nordvpn",
        "mullvad",
        "protonvpn",
        "warp",
        "sing-box",
        "nekoray",
    ),
    "browser": ("vivaldi", "chrome", "msedge", "firefox", "brave", "opera"),
    "браузер": ("vivaldi", "chrome", "msedge", "firefox", "brave", "opera"),
    "telegram": ("telegram",),
    "tg": ("telegram",),
    "тг": ("telegram",),
    "discord": ("discord",),
    "steam": ("steam",),
    "spotify": ("spotify",),
    "cursor": ("cursor",),
}

# Preferred desktop processes for known apps (never a browser tab title).
_NATIVE_PROCESSES: dict[str, tuple[str, ...]] = {
    "telegram": ("telegram.exe",),
    "tg": ("telegram.exe",),
    "тг": ("telegram.exe",),
    "discord": ("discord.exe", "update.exe"),
    "steam": ("steam.exe", "steamwebhelper.exe"),
    "spotify": ("spotify.exe",),
    "cursor": ("cursor.exe",),
    "hiddify": ("hiddify.exe",),
    "vpn": (
        "hiddify.exe",
        "clash.exe",
        "clash for windows.exe",
        "v2rayn.exe",
        "wireguard.exe",
    ),
    "впн": (
        "hiddify.exe",
        "clash.exe",
        "v2rayn.exe",
        "wireguard.exe",
    ),
}

_BROWSER_PROCESSES = {
    "vivaldi.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "opera_stable.exe",
    "iexplore.exe",
}


def _needles_for_query(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return []
    needles = [q]
    for alias, targets in QUERY_ALIASES.items():
        if q == alias or alias in q.split() or q in alias:
            needles.extend(targets)
        if alias in q:
            needles.extend(targets)
    seen: set[str] = set()
    out: list[str] = []
    for n in needles:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _native_procs_for_query(query: str) -> set[str]:
    q = (query or "").strip().lower()
    found: set[str] = set()
    for key, procs in _NATIVE_PROCESSES.items():
        if q == key or key in q.split() or key in q:
            found.update(procs)
    # Also when query expands via aliases to "telegram"
    for needle in _needles_for_query(query):
        if needle in _NATIVE_PROCESSES:
            found.update(_NATIVE_PROCESSES[needle])
    return found


def find_window(query: str, *, limit: int = 28, native_only: bool = False) -> dict[str, Any] | None:
    """Best open-window match. Prefers native app process over browser tabs."""
    needles = _needles_for_query(query)
    if not needles:
        return None
    native_procs = _native_procs_for_query(query)
    windows = list_visible_windows(limit=limit)

    best_native: tuple[int, dict[str, Any]] | None = None
    best_any: tuple[int, dict[str, Any]] | None = None

    for win in windows:
        title = str(win.get("title") or "")
        proc = str(win.get("process_name") or "")
        proc_l = proc.lower()
        title_l = title.lower()
        hay = f"{title_l} {proc_l}"
        matched = any(needle in hay for needle in needles)
        if not matched and proc_l not in native_procs:
            continue
        if native_procs and proc_l in native_procs:
            matched = True
        if not matched:
            continue

        is_browser = proc_l in _BROWSER_PROCESSES
        # Title-only hit inside a browser (e.g. "Telegram Messenger - Vivaldi") is not the app.
        if is_browser and native_procs:
            continue
        if native_only and is_browser:
            continue

        score = 0
        for needle in needles:
            if needle in proc_l:
                score += 50 + len(needle)
            elif needle in title_l:
                score += 10 + len(needle)
        if proc_l in native_procs:
            score += 100
        if is_browser:
            score -= 80

        cand = (score, win)
        if proc_l in native_procs or (native_procs and not is_browser and matched):
            if best_native is None or score > best_native[0]:
                best_native = cand
        if best_any is None or score > best_any[0]:
            best_any = cand

    if best_native is not None:
        return best_native[1]
    if native_only:
        return None
    # If query is a known desktop app (has native procs), never fall back to browser tabs.
    if native_procs:
        return None
    return best_any[1] if best_any else None


def format_open_windows_hint(*, limit: int = 14) -> str:
    windows = list_visible_windows(limit=limit)
    if not windows:
        return "(no open windows listed)"
    lines = []
    for win in windows:
        title = str(win.get("title") or "")[:80]
        proc = str(win.get("process_name") or "?")
        lines.append(f"- {title} ({proc})")
    alias_note = (
        "Alias hints: 'vpn'→Hiddify/Clash/… by process; "
        "'tg'/telegram→Telegram.exe only (NOT a Vivaldi/Chrome tab titled Telegram). "
        "For 'open tg' use launch_app id=telegram if Telegram.exe is not open."
    )
    return "Open windows now:\n" + "\n".join(lines) + "\n" + alias_note
