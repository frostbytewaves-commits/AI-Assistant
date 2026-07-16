# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — windowed onedir build of AI-Assistant."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH).resolve()

datas: list = []
binaries: list = []
hiddenimports: list = [
    "assistant",
    "assistant.act",
    "assistant.act.plugin",
    "assistant.core",
    "assistant.memory",
    "game_data",
    "game_data.paths",
    "plugins",
    "plugins.system",
    "tkinter",
    "PIL",
    "PIL._tkinter_finder",
    "numpy",
    "requests",
    "sounddevice",
    "keyboard",
    "comtypes",
    "comtypes.stream",
    "edge_tts",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "speech_recognition",
    "pytesseract",
    "duckduckgo_search",
    "faster_whisper",
    "ctranslate2",
    "av",
    "tokenizers",
    "huggingface_hub",
]

for pkg in ("faster_whisper", "ctranslate2", "av", "tokenizers"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        hiddenimports += collect_submodules(pkg)

# Bundle plugin packages + thin game_data helpers
datas += [
    (str(ROOT / "plugins"), "plugins"),
    (str(ROOT / "game_data"), "game_data"),
    (str(ROOT / "local_config.json.example"), "."),
]

a = Analysis(
    [str(ROOT / "run_assistant.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI-Assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed — no terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AI-Assistant",
)
