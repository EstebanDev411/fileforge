"""
paths.py
---------
Central path resolver that works correctly in BOTH environments:
  - Development:  python main.py          (normal Python)
  - Production:   FileForge.exe           (PyInstaller --onefile)

The problem PyInstaller creates
--------------------------------
When running as --onefile, Python files are extracted to a temporary
folder stored in sys._MEIPASS (e.g. C:\\Users\\John\\AppData\\Local\\Temp\\_MEI123).
This folder is DELETED when the .exe closes.

That means:
  - extensions.json (read-only)  → safe to read from _MEIPASS
  - config.json     (writable)   → MUST be saved to AppData, not _MEIPASS
  - history.json    (writable)   → MUST be saved to AppData, not _MEIPASS
  - log.txt         (writable)   → MUST be saved to AppData, not _MEIPASS

Usage
-----
    from paths import Paths

    cfg  = Paths.config()        # writable config.json
    log  = Paths.log()           # writable log.txt
    hist = Paths.history()       # writable history.json
    ext  = Paths.extensions()    # read-only extensions.json
"""

from __future__ import annotations

import sys
from pathlib import Path


def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _meipass() -> Path:
    """Temporary extraction folder inside the .exe."""
    return Path(sys._MEIPASS)  # type: ignore[attr-defined]


def _appdata() -> Path:
    """
    Persistent writable folder for user data.
      Windows : C:\\Users\\<user>\\AppData\\Roaming\\FileForge
      Linux   : ~/.config/FileForge
      macOS   : ~/Library/Application Support/FileForge
    """
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    folder = base / "FileForge"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _dev_root() -> Path:
    """Project root when running in development (not frozen)."""
    return Path(__file__).parent


class Paths:
    """
    Static helpers that always return the correct absolute Path,
    regardless of whether the app is running in dev or as a .exe.
    """

    # ── Read-only (bundled in the .exe via --add-data) ─────────────────

    @staticmethod
    def extensions() -> Path:
        """data/extensions.json — bundled, read-only."""
        if _is_frozen():
            return _meipass() / "data" / "extensions.json"
        return _dev_root() / "data" / "extensions.json"

    @staticmethod
    def bundled_config() -> Path:
        """config/config.json inside the bundle — used as defaults template."""
        if _is_frozen():
            return _meipass() / "config" / "config.json"
        return _dev_root() / "config" / "config.json"

    # ── Writable (always in AppData when frozen, local when dev) ───────

    @staticmethod
    def writable_root() -> Path:
        """Root of the writable data folder."""
        if _is_frozen():
            return _appdata()
        return _dev_root()

    @staticmethod
    def config() -> Path:
        """Writable config.json — survives .exe restarts."""
        path = Paths.writable_root() / "config" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def log() -> Path:
        """Writable log.txt inside logs/."""
        path = Paths.writable_root() / "logs" / "log.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def history() -> Path:
        """Writable history.json inside history/."""
        path = Paths.writable_root() / "history" / "history.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def resources() -> Path:
        """Resources folder (icons, themes)."""
        if _is_frozen():
            return _meipass() / "resources"
        return _dev_root() / "resources"

    @staticmethod
    def icon() -> Path:
        """App icon .ico file."""
        return Paths.resources() / "icons" / "fileforge.ico"

    @staticmethod
    def locale() -> Path:
        """Locale folder containing .xml translation files."""
        if _is_frozen():
            return _meipass() / "locale"
        return _dev_root() / "locale"
