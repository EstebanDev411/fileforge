"""
core/heuristics.py
-------------------
Smart sub-classification of FileEntry objects beyond basic extension matching.

Detects:
  - Screenshots  → sub_category = "Images/Screenshots"
  - Memes        → sub_category = "Images/Memes"
  - Large files  → sub_category = "_LargeFiles/<category>"

Detection signals used (no image decoding needed):
  1. Filename patterns   – case-insensitive substring / prefix matching
  2. Parent folder name  – common screenshot/download source folders
  3. File size vs. thresholds per category (large file detection)

Design principles:
  - Zero external dependencies (no Pillow, no OpenCV)
  - Stateless after __init__ → thread-safe
  - Non-destructive: only sets entry.sub_category, never changes entry.category
  - Config-driven: all patterns and thresholds come from config.json

Usage:
    from core.heuristics import Heuristics
    from core.scanner import FileEntry

    h = Heuristics()
    h.apply(entry)          # sets entry.sub_category in-place
    h.apply_all(entries)    # bulk in-place
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from system.config import Config
from system.logger import get_logger

log = get_logger(__name__)

# Image extensions eligible for screenshot / meme detection
_IMAGE_EXTS = frozenset([
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".tiff", ".tif", ".heic", ".heif", ".avif",
])


class Heuristics:
    """
    Rule-based sub-classifier for screenshots, memes, and large files.

    All rules are loaded from config.json at init time.
    Call reload() to hot-reload after config changes.
    """

    def __init__(self) -> None:
        self._screenshot_patterns: list[str] = []
        self._screenshot_folders:  set[str]  = set()
        self._screenshot_dest:     str        = "Images/Screenshots"
        self._screenshot_enabled:  bool       = True

        self._meme_patterns: list[str] = []
        self._meme_dest:     str        = "Images/Memes"
        self._meme_enabled:  bool       = True

        self._large_enabled:    bool         = True
        self._large_dest:       str          = "_LargeFiles"
        self._large_thresholds: dict[str, float] = {}

        self._load_config()

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    def apply(self, entry: "FileEntry") -> None:  # type: ignore[name-defined]
        """
        Analyse *entry* and set entry.sub_category in-place.

        Rules are evaluated in priority order:
          1. Screenshot by filename pattern  (strongest signal)
          2. Meme by filename pattern        (name is authoritative)
          3. Screenshot by source folder     (weaker, contextual signal)
          4. Large file                      (applies to all categories)

        If no rule fires, sub_category is left unchanged (empty string).
        """
        if self._is_image(entry):
            # ── 1. Screenshot: explicit name pattern ─────────────────
            if self._screenshot_enabled and self._matches_screenshot_name(entry):
                entry.sub_category = self._screenshot_dest
                return

            # ── 2. Meme: filename keyword ─────────────────────────────
            if self._meme_enabled and self._matches_meme(entry):
                entry.sub_category = self._meme_dest
                return

            # ── 3. Screenshot: contextual folder signal ───────────────
            if self._screenshot_enabled and self._matches_screenshot_folder(entry):
                entry.sub_category = self._screenshot_dest
                return

        # ── 4. Large file (all categories) ───────────────────────────
        if self._large_enabled and self._is_large(entry):
            entry.sub_category = f"{self._large_dest}/{entry.category}"
            return

    def apply_all(self, entries: list) -> None:
        """Apply heuristics to every entry in the list in-place."""
        screenshots = memes = large = 0
        for entry in entries:
            before = entry.sub_category
            self.apply(entry)
            after = entry.sub_category
            if after != before:
                if "Screenshot" in after:
                    screenshots += 1
                elif "Meme" in after:
                    memes += 1
                elif self._large_dest in after:
                    large += 1

        log.info(
            "Heuristics applied: %d screenshots, %d memes, %d large files "
            "(out of %d total entries)",
            screenshots, memes, large, len(entries),
        )

    def reload(self) -> None:
        """Hot-reload config (call after user edits config.json)."""
        self._load_config()
        log.info("Heuristics config reloaded")

    # ------------------------------------------------------------------ #
    #  Screenshot detection                                                 #
    # ------------------------------------------------------------------ #

    def _matches_screenshot_name(self, entry) -> bool:
        """Return True if filename contains a known screenshot pattern."""
        name_lower = entry.name.lower()
        for pattern in self._screenshot_patterns:
            if pattern in name_lower:
                log.debug("Screenshot by name pattern '%s': %s", pattern, entry.name)
                return True
        return False

    def _matches_screenshot_folder(self, entry) -> bool:
        """Return True if file lives in a known screenshot source folder."""
        parent_name = Path(entry.path).parent.name.lower()
        if parent_name in self._screenshot_folders:
            log.debug("Screenshot by folder '%s': %s", parent_name, entry.name)
            return True
        return False

    def _matches_screenshot(self, entry) -> bool:
        """Combined check (used by get_stats)."""
        return self._matches_screenshot_name(entry) or self._matches_screenshot_folder(entry)

    # ------------------------------------------------------------------ #
    #  Meme detection                                                       #
    # ------------------------------------------------------------------ #

    def _matches_meme(self, entry) -> bool:
        """
        Return True if the file is likely a meme.

        Signals:
          a) Filename contains a known meme keyword
        """
        name_lower = Path(entry.name).stem.lower()  # stem only, no extension

        for pattern in self._meme_patterns:
            if pattern in name_lower:
                log.debug("Meme by name pattern '%s': %s", pattern, entry.name)
                return True

        return False

    # ------------------------------------------------------------------ #
    #  Large file detection                                                 #
    # ------------------------------------------------------------------ #

    def _is_large(self, entry) -> bool:
        """
        Return True if the file exceeds the configured size threshold
        for its category.
        """
        cat_key = entry.category.lower()
        threshold_mb = self._large_thresholds.get(
            cat_key,
            self._large_thresholds.get("other", 500.0),
        )
        return entry.size_mb() > threshold_mb

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_image(entry) -> bool:
        return entry.extension.lower() in _IMAGE_EXTS

    def get_stats(self, entries: list) -> dict:
        """
        Dry-run: return counts of what would be classified without modifying entries.
        Useful for GUI preview. Does NOT modify any entry.
        """
        screenshots = memes = large = unchanged = 0

        for entry in entries:
            classified = False
            if self._is_image(entry):
                if self._screenshot_enabled and self._matches_screenshot_name(entry):
                    screenshots += 1
                    classified = True
                elif self._meme_enabled and self._matches_meme(entry):
                    memes += 1
                    classified = True
                elif self._screenshot_enabled and self._matches_screenshot_folder(entry):
                    screenshots += 1
                    classified = True

            if not classified and self._large_enabled and self._is_large(entry):
                large += 1
                classified = True

            if not classified:
                unchanged += 1

        return {
            "screenshots": screenshots,
            "memes": memes,
            "large_files": large,
            "unchanged": unchanged,
            "total": len(entries),
        }

    # ------------------------------------------------------------------ #
    #  Config loading                                                        #
    # ------------------------------------------------------------------ #

    def _load_config(self) -> None:
        """Pull all heuristic parameters from Config."""

        # ── Screenshots ─────────────────────────────────────────────
        ss_cfg = Config.get("heuristics.screenshots", {})
        self._screenshot_enabled  = ss_cfg.get("enabled", True)
        self._screenshot_dest     = ss_cfg.get("destination", "Images/Screenshots")
        raw_patterns              = ss_cfg.get("name_patterns", [])
        self._screenshot_patterns = [p.lower() for p in raw_patterns]
        raw_folders               = ss_cfg.get("source_folders", [])
        self._screenshot_folders  = {f.lower() for f in raw_folders}

        # ── Memes ────────────────────────────────────────────────────
        meme_cfg = Config.get("heuristics.memes", {})
        self._meme_enabled  = meme_cfg.get("enabled", True)
        self._meme_dest     = meme_cfg.get("destination", "Images/Memes")
        raw_meme            = meme_cfg.get("name_patterns", [])
        self._meme_patterns = [p.lower() for p in raw_meme]

        # ── Large files ──────────────────────────────────────────────
        lf_cfg = Config.get("large_files", {})
        self._large_enabled = lf_cfg.get("enabled", True)
        self._large_dest    = lf_cfg.get("destination", "_LargeFiles")

        raw_thresholds = Config.get("large_file_thresholds", {})
        self._large_thresholds = {
            k.lower(): float(v) for k, v in raw_thresholds.items()
        }

        log.debug(
            "Heuristics loaded — screenshot patterns: %d, folder triggers: %d, "
            "meme patterns: %d, large thresholds: %d",
            len(self._screenshot_patterns),
            len(self._screenshot_folders),
            len(self._meme_patterns),
            len(self._large_thresholds),
        )
