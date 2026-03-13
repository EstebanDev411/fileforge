"""
system/history.py
------------------
Persists every FileForge operation in history/history.json.
Supports undo by storing original paths.

Usage:
    from system.history import History

    entry_id = History.record(
        action="organize",
        source="C:/Downloads",
        files_affected=320,
        details=[{"from": "...", "to": "..."}]
    )
    History.undo(entry_id)
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from paths import Paths


class History:
    """Thread-safe history manager."""

    _lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Write                                                                #
    # ------------------------------------------------------------------ #

    @classmethod
    def record(
        cls,
        action: str,
        source: str = "",
        destination: str = "",
        files_affected: int = 0,
        errors: int = 0,
        details: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Save an operation entry and return its UUID.

        Parameters
        ----------
        action : str
            One of: scan | organize | move | delete | duplicate | undo
        source : str
            Source directory or file.
        destination : str
            Destination directory (if applicable).
        files_affected : int
            Number of files processed.
        errors : int
            Number of errors encountered.
        details : list[dict]
            Per-file operation log: [{"from": "...", "to": "...", "action": "..."}]
        """
        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "source": source,
            "destination": destination,
            "files_affected": files_affected,
            "errors": errors,
            "details": details or [],
        }

        with cls._lock:
            data = cls._load()
            data["entries"].insert(0, entry)  # newest first

            # Trim to max_entries
            try:
                from system.config import Config
                max_entries = Config.get("history.max_entries", 500)
            except Exception:
                max_entries = 500
            data["entries"] = data["entries"][:max_entries]

            cls._save(data)

        return entry_id

    # ------------------------------------------------------------------ #
    #  Read                                                                 #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_all(cls) -> list[dict[str, Any]]:
        """Return all history entries (newest first)."""
        with cls._lock:
            return cls._load()["entries"]

    @classmethod
    def get_entry(cls, entry_id: str) -> dict[str, Any] | None:
        """Return a single entry by UUID."""
        with cls._lock:
            for entry in cls._load()["entries"]:
                if entry["id"] == entry_id:
                    return entry
        return None

    # ------------------------------------------------------------------ #
    #  Undo                                                                 #
    # ------------------------------------------------------------------ #

    @classmethod
    def undo(cls, entry_id: str) -> tuple[int, list[str]]:
        """
        Attempt to reverse an organize/move operation.

        Returns
        -------
        (reversed_count, errors_list)
        """
        import shutil
        from system.logger import get_logger

        log = get_logger(__name__)
        entry = cls.get_entry(entry_id)

        if not entry:
            return 0, [f"Entry {entry_id} not found"]

        if entry["action"] not in ("organize", "move"):
            return 0, [f"Cannot undo action type: {entry['action']}"]

        reversed_count = 0
        errors: list[str] = []

        for op in entry.get("details", []):
            src = op.get("to")
            dst = op.get("from")
            if not src or not dst:
                continue
            try:
                if Path(src).exists():
                    Path(dst).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    reversed_count += 1
                else:
                    errors.append(f"Missing: {src}")
            except Exception as exc:
                errors.append(f"Error reversing {src}: {exc}")
                log.error("Undo error: %s", exc)

        # Record the undo itself
        cls.record(
            action="undo",
            source=entry.get("destination", ""),
            destination=entry.get("source", ""),
            files_affected=reversed_count,
            errors=len(errors),
        )
        return reversed_count, errors

    # ------------------------------------------------------------------ #
    #  Clear                                                                #
    # ------------------------------------------------------------------ #

    @classmethod
    def clear(cls) -> None:
        """Delete all history entries."""
        with cls._lock:
            cls._save({"version": "1.0.0", "entries": []})

    # ------------------------------------------------------------------ #
    #  Internal I/O                                                         #
    # ------------------------------------------------------------------ #

    @classmethod
    def _load(cls) -> dict[str, Any]:
        history_path = Paths.history()
        if not history_path.exists():
            return {"version": "1.0.0", "entries": []}
        try:
            with open(history_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {"version": "1.0.0", "entries": []}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        history_path = Paths.history()
        with open(history_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
