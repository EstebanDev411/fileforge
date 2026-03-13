"""
core/organizer.py
------------------
Moves or copies classified FileEntry objects into a structured output folder.

Features:
- Supports move, copy, and dry_run modes
- Conflict resolution: rename (default), skip, overwrite
- Progress callback
- Cancellation support
- Full operation log for History + undo support
- Thread-safe (can be called from background thread)

Output structure:
    <destination>/
        Images/
            Screenshots/   ← sub_category from heuristics
            Memes/
        Videos/
        Documents/
        _LargeFiles/
        _Duplicates/
        Other/

Usage:
    from core.organizer import Organizer, OrganizeResult
    from core.scanner import FileEntry

    org = Organizer(destination="C:/Organized")
    result = org.organize(entries)
    print(result.moved, result.errors)
"""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from system.config import Config
from system.history import History
from system.logger import get_logger

log = get_logger(__name__)

ProgressCallback = Callable[[int, int, str], None]  # (done, total, current_file)


# ──────────────────────────────────────────────────────────────────────────────
#  Result object
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class OrganizeResult:
    """Summary of a completed organize operation."""
    total: int = 0
    moved: int = 0
    copied: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = False
    details: list[dict] = field(default_factory=list)

    def __str__(self) -> str:
        action = "Would move" if self.dry_run else "Moved"
        return (
            f"[Organize] {action} {self.moved} files | "
            f"Skipped {self.skipped} | Errors {self.errors} | "
            f"Total {self.total}"
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Organizer
# ──────────────────────────────────────────────────────────────────────────────

class Organizer:
    """
    Moves/copies a list of FileEntry objects into a categorised folder structure.

    Parameters
    ----------
    destination : str | Path
        Root folder where organised files will be placed.
        Will be created if it does not exist.
    mode : str
        'move' | 'copy'  (default: from config)
    dry_run : bool
        If True, compute what would happen but don't touch the filesystem.
    conflict : str
        'rename' | 'skip' | 'overwrite'
    progress_callback : callable
        Called as (done, total, current_file_path).
    """

    def __init__(
        self,
        destination: str | Path,
        mode: Optional[str] = None,
        dry_run: Optional[bool] = None,
        conflict: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.destination = Path(destination)
        self.mode = mode or Config.get("organize.mode", "move")
        self.dry_run = dry_run if dry_run is not None else Config.get("organize.dry_run", False)
        self.conflict = conflict or Config.get("organize.handle_conflicts", "rename")
        self._progress_callback = progress_callback
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    def organize(self, entries: list, source_root: str = "") -> OrganizeResult:
        """
        Organise *entries* into self.destination.

        Parameters
        ----------
        entries : list[FileEntry]
            Pre-classified FileEntry objects (category must be set).
        source_root : str
            Original scan root — recorded in history.

        Returns
        -------
        OrganizeResult
        """
        self._cancel_event.clear()
        result = OrganizeResult(total=len(entries), dry_run=self.dry_run)

        if not self.dry_run:
            self.destination.mkdir(parents=True, exist_ok=True)

        log.info(
            "Organize started: %d files → %s [mode=%s, dry_run=%s]",
            len(entries), self.destination, self.mode, self.dry_run
        )

        for i, entry in enumerate(entries):
            if self._cancel_event.is_set():
                log.info("Organize cancelled after %d files", i)
                break

            self._fire_progress(i, len(entries), entry.path)

            dest_path = self._resolve_destination(entry)

            detail = {
                "from": entry.path,
                "to": str(dest_path),
                "action": self.mode,
                "category": entry.category,
                "sub_category": entry.sub_category,
            }

            if self.dry_run:
                result.moved += 1
                detail["action"] = f"dry_run:{self.mode}"
                result.details.append(detail)
                continue

            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                resolved = self._handle_conflict(Path(entry.path), dest_path)

                if resolved is None:
                    # skip
                    result.skipped += 1
                    detail["action"] = "skipped"
                    result.details.append(detail)
                    continue

                detail["to"] = str(resolved)

                if self.mode == "move":
                    shutil.move(entry.path, str(resolved))
                    result.moved += 1
                else:
                    shutil.copy2(entry.path, str(resolved))
                    result.copied += 1

                result.details.append(detail)

            except PermissionError as exc:
                log.warning("Permission denied: %s → %s", entry.path, exc)
                result.errors += 1
                detail["action"] = f"error:{exc}"
                result.details.append(detail)
            except OSError as exc:
                log.error("OS error organising %s: %s", entry.path, exc)
                result.errors += 1
                detail["action"] = f"error:{exc}"
                result.details.append(detail)

        self._fire_progress(len(entries), len(entries), "")

        # Persist to history
        if not self.dry_run and Config.get("history.enabled", True):
            History.record(
                action=self.mode,
                source=source_root,
                destination=str(self.destination),
                files_affected=result.moved + result.copied,
                errors=result.errors,
                details=result.details,
            )

        log.info(str(result))
        return result

    def cancel(self) -> None:
        """Request cancellation of an in-progress organize operation."""
        self._cancel_event.set()

    # ------------------------------------------------------------------ #
    #  Destination resolution                                               #
    # ------------------------------------------------------------------ #

    def _resolve_destination(self, entry) -> Path:
        """
        Build the target path for a FileEntry.

        Logic:
            destination / category / sub_category / filename
            OR
            destination / _LargeFiles / category / filename   (if large)
        """
        # Large files go to a separate top-level folder
        large_dest = Config.get("large_files.destination", "_LargeFiles")
        if self._is_large(entry):
            folder = self.destination / large_dest / entry.category
        elif entry.sub_category:
            # e.g. "Images/Screenshots" → two levels
            parts = entry.sub_category.replace("\\", "/").split("/")
            folder = self.destination.joinpath(*parts)
        else:
            folder = self.destination / entry.category

        return folder / entry.name

    def _is_large(self, entry) -> bool:
        """Check if entry exceeds the configured large-file threshold."""
        if not Config.get("large_files.enabled", True):
            return False

        thresholds = Config.get("large_file_thresholds", {})
        cat_lower = entry.category.lower()

        # Try specific category match first, then 'other'
        limit_mb = thresholds.get(cat_lower, thresholds.get("other", 500))
        return entry.size_mb() > float(limit_mb)

    # ------------------------------------------------------------------ #
    #  Conflict resolution                                                  #
    # ------------------------------------------------------------------ #

    def _handle_conflict(self, src: Path, dest: Path) -> Optional[Path]:
        """
        Return the final destination path after resolving a name conflict.

        Returns None if the file should be skipped.
        """
        if not dest.exists():
            return dest

        if self.conflict == "overwrite":
            return dest

        if self.conflict == "skip":
            log.debug("Skipping (conflict): %s", dest)
            return None

        # Default: rename → append (1), (2), ...
        stem = dest.stem
        suffix = dest.suffix
        parent = dest.parent
        counter = 1
        while True:
            new_dest = parent / f"{stem} ({counter}){suffix}"
            if not new_dest.exists():
                return new_dest
            counter += 1
            if counter > 9999:
                log.error("Too many conflicts for %s", dest)
                return None

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _fire_progress(self, done: int, total: int, current: str) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(done, total, current)
            except Exception:
                pass
