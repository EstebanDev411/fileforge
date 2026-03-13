"""
system/config.py
-----------------
Singleton configuration manager.
Loads config/config.json and provides typed, thread-safe access.
Supports live reload (GUI can edit config without restart).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


from paths import Paths


class Config:
    """
    Thread-safe singleton configuration manager.

    Usage:
        Config.initialize()               # call once at startup
        Config.get("scan.max_workers")    # dot-notation access
        Config.set("gui.theme", "light")  # write in-memory (+ optional save)
        Config.save()                     # persist to disk
    """

    _instance: Config | None = None
    _lock: threading.Lock = threading.Lock()
    _data: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    #  Singleton bootstrap                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def initialize(cls, config_path: Path | None = None) -> None:
        """Load the config file. Call once at application startup."""
        with cls._lock:
            # Use explicit path, or the writable path from Paths
            path = Path(config_path) if config_path else Paths.config()

            if not path.exists():
                # First run: seed from the bundled template if available
                template = Paths.bundled_config()
                path.parent.mkdir(parents=True, exist_ok=True)
                if template.exists() and template != path:
                    with open(template, "r", encoding="utf-8") as fh:
                        loaded = json.load(fh)
                    cls._data = cls._deep_merge(cls._defaults(), loaded)
                else:
                    cls._data = cls._defaults()
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(cls._data, fh, indent=2)
            else:
                with open(path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                # Merge with defaults so new keys are never missing
                cls._data = cls._deep_merge(cls._defaults(), loaded)

            cls._config_path = path

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Retrieve a value using dot-notation.

        Example:
            Config.get("scan.max_workers")   → 0
            Config.get("missing.key", 42)    → 42
        """
        with cls._lock:
            keys = key.split(".")
            node = cls._data
            try:
                for k in keys:
                    node = node[k]
                return node
            except (KeyError, TypeError):
                return default

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """
        Write a value using dot-notation (in-memory only).
        Call Config.save() to persist.
        """
        with cls._lock:
            keys = key.split(".")
            node = cls._data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value

    @classmethod
    def all(cls) -> dict[str, Any]:
        """Return a shallow copy of the full config dict."""
        with cls._lock:
            return dict(cls._data)

    @classmethod
    def save(cls) -> None:
        """Persist current in-memory config to disk."""
        with cls._lock:
            cls._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cls._config_path, "w", encoding="utf-8") as fh:
                json.dump(cls._data, fh, indent=2)

    @classmethod
    def reload(cls) -> None:
        """Re-read the config file from disk."""
        with cls._lock:
            with open(cls._config_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            cls._data = cls._deep_merge(cls._defaults(), loaded)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base (non-destructive)."""
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _defaults() -> dict[str, Any]:
        """Minimal safe defaults — used when config.json is absent."""
        return {
            "version": "1.0.0",
            "app_name": "FileForge",
            "scan": {
                "max_depth": -1,
                "follow_symlinks": False,
                "skip_hidden": True,
                "skip_system": True,
                "max_workers": 0,
                "skip_directories": [
                    "$RECYCLE.BIN", "System Volume Information",
                    ".git", "__pycache__", "node_modules"
                ]
            },
            "organize": {
                "mode": "move",
                "create_category_folders": True,
                "handle_conflicts": "rename",
                "dry_run": False,
                "output_folder_name": "_Organized"
            },
            "duplicates": {
                "enabled": True,
                "strategy": "move_to_folder",
                "duplicates_folder": "_Duplicates",
                "keep": "newest",
                "min_size_bytes": 1024
            },
            "heuristics": {
                "screenshots": {
                    "enabled": True,
                    "destination": "Images/Screenshots",
                    "name_patterns": ["screenshot", "captura", "img_", "screen shot"],
                    "source_folders": ["Downloads", "Desktop", "WhatsApp Images", "Screenshots"]
                },
                "memes": {
                    "enabled": True,
                    "destination": "Images/Memes",
                    "name_patterns": ["meme", "funny", "lol", "wtf"]
                }
            },
            "large_file_thresholds": {
                "documents": 100,
                "images": 500,
                "photoshop": 2000,
                "videos": 1000,
                "audio": 200,
                "archives": 4000,
                "other": 500
            },
            "large_files": {"enabled": True, "destination": "_LargeFiles"},
            "history": {"max_entries": 500, "enabled": True},
            "logging": {
                "level": "INFO",
                "max_file_size_mb": 10,
                "backup_count": 5,
                "console_output": True
            },
            "gui": {
                "theme": "dark",
                "language": "en",
                "window_width": 1280,
                "window_height": 800,
                "remember_last_folder": True
            }
        }
