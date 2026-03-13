"""
core/classifier.py
-------------------
Classifies FileEntry objects by extension using data/extensions.json.

Design:
- Loads extension map once into memory at init (O(1) lookup via dict)
- Stateless: safe to use from multiple threads simultaneously
- Handles edge cases: no extension, unknown extension, mixed case
- Supports bulk classification of FileEntry lists in-place

Usage:
    from core.classifier import Classifier
    from core.scanner import FileEntry

    clf = Classifier()
    clf.classify(entry)          # sets entry.category in-place
    clf.classify_all(entries)    # bulk in-place classification
    cat = clf.get_category(".psd")  # → "Design"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from system.logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).parent.parent
_EXT_PATH = _ROOT / "data" / "extensions.json"

try:
    from paths import Paths as _Paths
    _EXT_PATH = _Paths.extensions()
except ImportError:
    pass


class Classifier:
    """
    Extension-based file classifier.

    Loads data/extensions.json and builds an inverted index:
        { ".jpg": "Images", ".mp4": "Videos", ... }

    Thread-safe: read-only after __init__.
    """

    def __init__(self, extensions_path: Optional[Path] = None) -> None:
        path = extensions_path or _EXT_PATH
        self._ext_map: dict[str, str] = {}      # ".ext" → "Category"
        self._categories: list[str] = []
        self._load(path)

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    def classify(self, entry: "FileEntry") -> None:  # type: ignore[name-defined]
        """
        Assign entry.category in-place based on file extension.
        Safe to call from any thread.
        """
        entry.category = self.get_category(entry.extension)

    def classify_all(self, entries: list) -> None:
        """
        Classify a list of FileEntry objects in-place.
        No threads spawned — caller decides parallelism.
        """
        for entry in entries:
            entry.category = self.get_category(entry.extension)

    def get_category(self, extension: str) -> str:
        """
        Return the category name for a given extension string.

        Parameters
        ----------
        extension : str
            Extension WITH or WITHOUT leading dot, any case.
            Examples: ".JPG", "jpg", ".mp4"

        Returns
        -------
        str
            Category name or "Other" if unknown.
        """
        if not extension:
            return "Other"
        # Normalise: lowercase, ensure leading dot
        ext = extension.lower()
        if not ext.startswith("."):
            ext = "." + ext
        return self._ext_map.get(ext, "Other")

    @property
    def categories(self) -> list[str]:
        """All known category names."""
        return list(self._categories)

    @property
    def total_extensions(self) -> int:
        """Total number of registered extensions."""
        return len(self._ext_map)

    def extensions_for(self, category: str) -> list[str]:
        """Return all extensions that map to *category*."""
        return [ext for ext, cat in self._ext_map.items() if cat == category]

    def reload(self, extensions_path: Optional[Path] = None) -> None:
        """Hot-reload extensions from disk (e.g. after user edits the JSON)."""
        path = extensions_path or _EXT_PATH
        self._ext_map.clear()
        self._categories.clear()
        self._load(path)
        log.info("Classifier reloaded: %d extensions", self.total_extensions)

    # ------------------------------------------------------------------ #
    #  Internal                                                             #
    # ------------------------------------------------------------------ #

    def _load(self, path: Path) -> None:
        """
        Parse extensions.json and build the inverted lookup dict.

        Expected format:
            { "Images": [".jpg", ".png", ...], "Videos": [...], ... }
        """
        if not path.exists():
            log.error("extensions.json not found at %s", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data: dict[str, list[str]] = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to load extensions.json: %s", exc)
            return

        for category, exts in data.items():
            if category == "Other":
                continue  # 'Other' is the fallback, not a registered category
            self._categories.append(category)
            for raw_ext in exts:
                ext = raw_ext.lower()
                if not ext.startswith("."):
                    ext = "." + ext
                if ext in self._ext_map:
                    log.debug(
                        "Extension %s already mapped to %s, overriding with %s",
                        ext, self._ext_map[ext], category
                    )
                self._ext_map[ext] = category

        log.info(
            "Classifier loaded: %d categories, %d extensions",
            len(self._categories),
            len(self._ext_map),
        )
