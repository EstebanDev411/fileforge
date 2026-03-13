"""
core/scanner.py
----------------
Massive file system scanner using os.scandir() + ThreadPoolExecutor.

Key features:
- Handles millions of files efficiently (streaming, no full list in RAM)
- Parallel subdirectory traversal
- Cancellation via threading.Event
- Progress callbacks (files found, current path)
- Graceful error handling (permissions, broken links)
- Configurable depth, hidden files, system dirs

Usage:
    from core.scanner import Scanner, FileEntry

    scanner = Scanner(progress_callback=lambda n, p: print(n, p))
    entries = scanner.scan("C:/Users/John/Documents")
    scanner.cancel()   # safe cancellation from another thread
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from system.config import Config
from system.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  Data model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FileEntry:
    """
    Lightweight representation of a single file discovered during scanning.
    Category and sub-category are filled in by classifier/heuristics.
    """
    path: str                          # Absolute path
    name: str                          # Filename with extension
    extension: str                     # Lower-case extension (e.g. '.jpg')
    size: int                          # Size in bytes
    modified: datetime                 # Last modification time
    created: datetime                  # Creation time (ctime on Linux = metadata change)
    category: str = "Other"            # Filled by Classifier
    sub_category: str = ""             # Filled by Heuristics (e.g. 'Screenshots')
    is_duplicate: bool = False         # Flagged by Duplicates module
    duplicate_group: str = ""          # Hash shared with duplicates

    @staticmethod
    def from_dir_entry(entry: os.DirEntry) -> "FileEntry":
        """Build a FileEntry from an os.DirEntry (fast — uses cached stat)."""
        try:
            stat = entry.stat(follow_symlinks=False)
            ext = Path(entry.name).suffix.lower()
            modified = datetime.fromtimestamp(stat.st_mtime)
            created  = datetime.fromtimestamp(stat.st_ctime)
            return FileEntry(
                path=entry.path,
                name=entry.name,
                extension=ext,
                size=stat.st_size,
                modified=modified,
                created=created,
            )
        except OSError as exc:
            log.warning("stat failed for %s: %s", entry.path, exc)
            return FileEntry(
                path=entry.path,
                name=entry.name,
                extension=Path(entry.name).suffix.lower(),
                size=0,
                modified=datetime.min,
                created=datetime.min,
            )

    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    def __repr__(self) -> str:
        return f"<FileEntry {self.name} ({self.size_mb():.2f} MB) [{self.category}]>"


# ──────────────────────────────────────────────────────────────────────────────
#  Scanner
# ──────────────────────────────────────────────────────────────────────────────

ProgressCallback = Callable[[int, str], None]


class Scanner:
    """
    Recursive file system scanner.

    Parameters
    ----------
    progress_callback : callable, optional
        Called periodically with (files_found, current_path).
        Must be thread-safe (will be called from worker threads).
    progress_interval : int
        How often to fire the callback (every N files found).
    """

    def __init__(
        self,
        progress_callback: Optional[ProgressCallback] = None,
        progress_interval: int = 250,
    ) -> None:
        self._progress_callback = progress_callback
        self._progress_interval = progress_interval
        self._cancel_event = threading.Event()
        self._counter_lock = threading.Lock()
        self._file_count = 0

        self._max_depth: int        = Config.get("scan.max_depth", -1)
        self._follow_symlinks: bool = Config.get("scan.follow_symlinks", False)
        self._skip_hidden: bool     = Config.get("scan.skip_hidden", True)
        self._skip_dirs: set        = set(
            d.lower() for d in Config.get("scan.skip_directories", [])
        )
        raw_workers: int = Config.get("scan.max_workers", 0)
        self._max_workers: int = raw_workers if raw_workers > 0 else (os.cpu_count() or 4)

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    def scan(self, root: str | Path) -> list[FileEntry]:
        """
        Scan *root* recursively and return all FileEntry objects found.

        Thread-safe. Can be cancelled via cancel().
        Errors (permission denied, broken links) are logged and skipped.
        """
        root = Path(root).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Directory not found: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")

        self._cancel_event.clear()
        self._file_count = 0
        results: list[FileEntry] = []
        lock = threading.Lock()

        log.info("Scan started: %s (workers=%d)", root, self._max_workers)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = []
            try:
                top_entries = list(os.scandir(root))
            except PermissionError as exc:
                log.error("Cannot scan root %s: %s", root, exc)
                return []

            root_files = []
            subdirs = []
            for entry in top_entries:
                if self._cancel_event.is_set():
                    break
                if self._should_skip(entry):
                    continue
                if entry.is_file(follow_symlinks=self._follow_symlinks):
                    root_files.append(FileEntry.from_dir_entry(entry))
                elif entry.is_dir(follow_symlinks=self._follow_symlinks):
                    subdirs.append(entry.path)

            with lock:
                results.extend(root_files)
            self._update_counter(len(root_files), str(root))

            for subdir in subdirs:
                if self._cancel_event.is_set():
                    break
                future = executor.submit(self._scan_subtree, subdir, depth=1)
                futures.append(future)

            for future in as_completed(futures):
                if self._cancel_event.is_set():
                    break
                try:
                    batch = future.result()
                    with lock:
                        results.extend(batch)
                except Exception as exc:
                    log.error("Scanner worker error: %s", exc)

        status = "cancelled" if self._cancel_event.is_set() else "complete"
        log.info("Scan %s: %d files found in %s", status, len(results), root)
        return results

    def scan_iter(self, root: str | Path) -> Iterator[FileEntry]:
        """Generator variant — yields FileEntry objects one by one."""
        root = Path(root).resolve()
        if not root.exists() or not root.is_dir():
            return
        self._cancel_event.clear()
        self._file_count = 0
        yield from self._scan_subtree_iter(str(root), depth=0)

    def cancel(self) -> None:
        """Signal all workers to stop as soon as possible."""
        self._cancel_event.set()
        log.info("Scan cancellation requested")

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def files_found(self) -> int:
        return self._file_count

    # ------------------------------------------------------------------ #
    #  Internal scanning                                                    #
    # ------------------------------------------------------------------ #

    def _scan_subtree(self, path: str, depth: int) -> list[FileEntry]:
        """Recursively scan a single subtree (runs in a worker thread)."""
        results: list[FileEntry] = []
        if self._cancel_event.is_set():
            return results
        if self._max_depth >= 0 and depth > self._max_depth:
            return results

        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._cancel_event.is_set():
                        return results
                    if self._should_skip(entry):
                        continue
                    try:
                        if entry.is_file(follow_symlinks=self._follow_symlinks):
                            results.append(FileEntry.from_dir_entry(entry))
                            self._update_counter(1, path)
                        elif entry.is_dir(follow_symlinks=self._follow_symlinks):
                            results.extend(self._scan_subtree(entry.path, depth + 1))
                    except OSError as exc:
                        log.warning("Entry error %s: %s", entry.path, exc)
        except PermissionError:
            log.warning("Permission denied: %s", path)
        except OSError as exc:
            log.warning("OS error scanning %s: %s", path, exc)

        return results

    def _scan_subtree_iter(self, path: str, depth: int) -> Iterator[FileEntry]:
        """Generator version of _scan_subtree."""
        if self._cancel_event.is_set():
            return
        if self._max_depth >= 0 and depth > self._max_depth:
            return

        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._cancel_event.is_set():
                        return
                    if self._should_skip(entry):
                        continue
                    try:
                        if entry.is_file(follow_symlinks=self._follow_symlinks):
                            self._update_counter(1, path)
                            yield FileEntry.from_dir_entry(entry)
                        elif entry.is_dir(follow_symlinks=self._follow_symlinks):
                            yield from self._scan_subtree_iter(entry.path, depth + 1)
                    except OSError as exc:
                        log.warning("Entry error %s: %s", entry.path, exc)
        except (PermissionError, OSError) as exc:
            log.warning("Scan error at %s: %s", path, exc)

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _should_skip(self, entry: os.DirEntry) -> bool:
        """Return True if this entry should be ignored."""
        name = entry.name
        if self._skip_hidden and name.startswith("."):
            return True
        if name.lower() in self._skip_dirs:
            return True
        return False

    def _update_counter(self, n: int, current_path: str) -> None:
        """Thread-safe counter update and callback firing."""
        with self._counter_lock:
            self._file_count += n
            count = self._file_count
        if self._progress_callback and count % self._progress_interval < n:
            try:
                self._progress_callback(count, current_path)
            except Exception:
                pass
