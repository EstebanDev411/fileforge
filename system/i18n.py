"""
system/i18n.py
---------------
Internationalization (i18n) engine for FileForge.

Loads translation strings from locale/<code>.xml and provides
dot-notation access: I18n.t("scan.title") → "Scan"

Supports runtime language switching — call I18n.load("es") and
the next call to I18n.t() returns Spanish strings.

XML format
----------
    <lang code="en" name="English">
      <group id="scan">
        <key id="title">Scan</key>
      </group>
    </lang>

Usage
-----
    from system.i18n import I18n

    I18n.initialize()                    # call once at startup
    I18n.load("es")                      # switch to Spanish
    label = I18n.t("scan.title")         # → "Escanear"
    label = I18n.t("scan.title", "en")   # force English
    langs  = I18n.available_languages()  # → [("en","English"), ("es","Español")]
"""

from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from system.logger import get_logger

log = get_logger(__name__)

# Resolve locale folder — works in dev and inside .exe (via paths.py)
def _locale_dir() -> Path:
    try:
        from paths import Paths
        base = Paths.writable_root()
        # If locale exists next to executable, use it; otherwise fall back to source
        locale = base / "locale"
        if locale.exists():
            return locale
    except ImportError:
        pass
    return Path(__file__).parent.parent / "locale"


class I18n:
    """
    Thread-safe singleton translation manager.

    Dot-notation key format: "<group_id>.<key_id>"
    Example: "scan.title", "common.btn_browse"

    Falls back to English if a key is missing in the active language.
    Falls back to the raw key string if not found in English either.
    """

    _lock:     threading.Lock    = threading.Lock()
    _data:     dict[str, dict[str, str]] = {}   # lang_code → {dot_key → value}
    _meta:     dict[str, str]    = {}           # lang_code → display name
    _active:   str               = "en"
    _fallback: str               = "en"

    # ------------------------------------------------------------------ #
    #  Bootstrap                                                            #
    # ------------------------------------------------------------------ #

    @classmethod
    def initialize(cls, lang: Optional[str] = None) -> None:
        """
        Load all available .xml files from the locale/ folder.
        Optionally set the active language immediately.

        Call once at application startup after Config.initialize().
        """
        with cls._lock:
            cls._data.clear()
            cls._meta.clear()
            locale_dir = _locale_dir()

            if not locale_dir.exists():
                log.warning("Locale directory not found: %s", locale_dir)
                cls._data["en"] = {}
                cls._meta["en"] = "English"
                return

            for xml_file in sorted(locale_dir.glob("*.xml")):
                try:
                    code, name, strings = cls._parse_xml(xml_file)
                    cls._data[code] = strings
                    cls._meta[code] = name
                    log.debug("Loaded locale: %s (%s) — %d keys", name, code, len(strings))
                except Exception as exc:
                    log.error("Failed to load locale %s: %s", xml_file.name, exc)

            # Determine active language
            if lang and lang in cls._data:
                cls._active = lang
            elif "en" in cls._data:
                cls._active = "en"
            elif cls._data:
                cls._active = next(iter(cls._data))

            total_keys = sum(len(v) for v in cls._data.values())
            log.info(
                "I18n initialized: %d languages, active=%s, total_keys=%d",
                len(cls._data), cls._active, total_keys,
            )

    # ------------------------------------------------------------------ #
    #  Translation                                                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def t(cls, key: str, lang: Optional[str] = None) -> str:
        """
        Translate a dot-notation key.

        Parameters
        ----------
        key  : str  — e.g. "scan.title"
        lang : str  — override active language for this call

        Returns
        -------
        Translated string, or English fallback, or the raw key if not found.
        """
        code = lang or cls._active

        with cls._lock:
            # Primary lookup
            value = cls._data.get(code, {}).get(key)
            if value is not None:
                return value

            # English fallback
            if code != cls._fallback:
                value = cls._data.get(cls._fallback, {}).get(key)
                if value is not None:
                    log.debug("i18n fallback to '%s' for key '%s'", cls._fallback, key)
                    return value

        # Last resort — return the key itself
        log.warning("i18n missing key: '%s' (lang=%s)", key, code)
        return key

    @classmethod
    def tf(cls, key: str, **kwargs) -> str:
        """
        Translate and format with keyword arguments.

        Example:
            I18n.tf("scan.complete", files=100, size=1.2, cats=6)
            → "Scan complete: 100 files, 1.2 GB, 6 categories"
        """
        raw = cls.t(key)
        try:
            return raw.format(**kwargs)
        except (KeyError, ValueError):
            return raw

    # ------------------------------------------------------------------ #
    #  Language management                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, lang_code: str) -> bool:
        """
        Switch the active language at runtime.

        Returns True if the language was found and loaded, False otherwise.
        """
        with cls._lock:
            if lang_code not in cls._data:
                log.warning("Language not available: %s", lang_code)
                return False
            cls._active = lang_code
            log.info("Language switched to: %s (%s)", lang_code, cls._meta.get(lang_code, "?"))
            return True

    @classmethod
    def active_language(cls) -> str:
        """Return the currently active language code (e.g. 'en')."""
        return cls._active

    @classmethod
    def active_language_name(cls) -> str:
        """Return the display name of the active language (e.g. 'English')."""
        with cls._lock:
            return cls._meta.get(cls._active, cls._active)

    @classmethod
    def available_languages(cls) -> list[tuple[str, str]]:
        """
        Return list of (code, name) tuples for all loaded languages,
        sorted alphabetically by name.

        Example: [("en", "English"), ("es", "Español")]
        """
        with cls._lock:
            return sorted(cls._meta.items(), key=lambda x: x[1])

    @classmethod
    def reload(cls) -> None:
        """Re-read all XML files from disk (useful after adding a new locale)."""
        active = cls._active
        cls.initialize(lang=active)

    # ------------------------------------------------------------------ #
    #  Internal XML parser                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def _parse_xml(cls, path: Path) -> tuple[str, str, dict[str, str]]:
        """
        Parse a locale XML file.

        Returns (code, display_name, {dot_key: value})
        """
        tree = ET.parse(path)
        root = tree.getroot()

        code = root.attrib.get("code", path.stem)
        name = root.attrib.get("name", code)
        strings: dict[str, str] = {}

        for group in root.findall("group"):
            group_id = group.attrib.get("id", "")
            for key_elem in group.findall("key"):
                key_id = key_elem.attrib.get("id", "")
                if group_id and key_id:
                    dot_key = f"{group_id}.{key_id}"
                    strings[dot_key] = (key_elem.text or "").strip()

        return code, name, strings
