"""
core/watcher.py
----------------
Folder watcher — monitors directories and auto-organizes new files.

Two backends (auto-selected):
  1. watchdog  — event-driven, instant response (pip install watchdog)
  2. polling   — scans every N seconds using os.scandir(), no extra deps

Debounce
--------
Files are not processed immediately on detection. A 2-second debounce
waits for the file to finish copying before touching it. Large files
(still growing) are re-queued until their size stabilizes.

Usage
-----
    from core.watcher import Watcher, WatchTarget

    target = WatchTarget(
        path="/home/user/Downloads",
        destination="/home/user/Organized",
        recursive=False,
    )

    w = Watcher(on_file=my_callback, on_log=print)
    w.add(target)
    w.start()
    # ... later ...
    w.stop()
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from system.config import Config
from system.logger import get_logger

log = get_logger(__name__)

# Try to import watchdog — fall back to polling silently
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
    _WATCHDOG = True
except ImportError:
    _WATCHDOG = False
    log.debug("watchdog not installed — using polling backend")


# ──────────────────────────────────────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class WatchTarget:
    """A folder to watch and its destination."""
    path:        str
    destination: str = ""           # empty = <path>/_Organized
    recursive:   bool = False
    enabled:     bool = True

    def resolved_dest(self) -> str:
        if self.destination.strip():
            return self.destination
        return str(Path(self.path) / Config.get("organize.output_folder_name", "_Organized"))


@dataclass
class WatchEvent:
    """Represents a file that was detected and processed."""
    path:        str
    dest:        str
    category:    str
    action:      str                # "moved" | "copied" | "skipped" | "error"
    timestamp:   float = field(default_factory=time.time)
    error:       str   = ""


# ──────────────────────────────────────────────────────────────────────────────
#  Debounce queue
# ──────────────────────────────────────────────────────────────────────────────

class _DebounceQueue:
    """
    Holds detected file paths and releases them after they stop growing.
    Prevents processing files that are still being written/copied.
    """

    STABLE_AFTER   = 2.0    # seconds without size change = file is ready
    CHECK_INTERVAL = 0.5    # how often to check sizes

    def __init__(self, on_ready: Callable[[str], None]):
        self._on_ready  = on_ready
        self._pending:  dict[str, tuple[float, int]] = {}  # path → (seen_at, last_size)
        self._lock      = threading.Lock()
        self._stop_ev   = threading.Event()
        self._thread    = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def push(self, path: str) -> None:
        with self._lock:
            size = self._file_size(path)
            self._pending[path] = (time.time(), size)

    def stop(self) -> None:
        self._stop_ev.set()

    def _run(self) -> None:
        while not self._stop_ev.is_set():
            time.sleep(self.CHECK_INTERVAL)
            now = time.time()
            ready = []
            with self._lock:
                for path, (seen_at, last_size) in list(self._pending.items()):
                    current = self._file_size(path)
                    if current < 0:                        # file gone
                        del self._pending[path]
                        continue
                    if current != last_size:               # still growing
                        self._pending[path] = (now, current)
                        continue
                    if now - seen_at >= self.STABLE_AFTER:  # stable long enough
                        ready.append(path)
                        del self._pending[path]

            for path in ready:
                try:
                    self._on_ready(path)
                except Exception as exc:
                    log.error("Debounce callback error for %s: %s", path, exc)

    @staticmethod
    def _file_size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return -1


# ──────────────────────────────────────────────────────────────────────────────
#  Watcher
# ──────────────────────────────────────────────────────────────────────────────

class Watcher:
    """
    Multi-target folder watcher with auto-organize on new files.

    Parameters
    ----------
    on_file : callable(WatchEvent)
        Called after each file is processed.
    on_log : callable(str)
        Called with log messages for the GUI log panel.
    poll_interval : int
        Seconds between polls (polling backend only). Default: 5.
    """

    def __init__(
        self,
        on_file:       Optional[Callable[[WatchEvent], None]] = None,
        on_log:        Optional[Callable[[str], None]]        = None,
        poll_interval: int = 5,
    ):
        self._on_file      = on_file or (lambda e: None)
        self._on_log       = on_log  or log.info
        self._poll_interval = poll_interval
        self._targets:     list[WatchTarget]  = []
        self._running      = False
        self._lock         = threading.Lock()
        self._stop_ev      = threading.Event()
        self._debounce     = _DebounceQueue(self._process_file)
        self._path_to_target: dict[str, WatchTarget] = {}

        # Polling: remember known files per target
        self._known_files: dict[str, set[str]] = {}

        # watchdog observer (if available)
        self._observer = None

        self.files_processed = 0
        self.files_errors    = 0

    # ------------------------------------------------------------------ #
    #  Target management                                                    #
    # ------------------------------------------------------------------ #

    def add(self, target: WatchTarget) -> None:
        """Add a folder to watch."""
        with self._lock:
            # Avoid duplicates
            existing = [t.path for t in self._targets]
            if target.path in existing:
                log.warning("Watcher: target already registered: %s", target.path)
                return
            self._targets.append(target)
            self._path_to_target[target.path] = target
            self._known_files[target.path] = self._snapshot(target.path, target.recursive)
            log.info("Watcher: added target %s → %s", target.path, target.resolved_dest())

        if self._running:
            self._mount_target(target)

    def remove(self, path: str) -> None:
        """Stop watching a folder."""
        with self._lock:
            self._targets = [t for t in self._targets if t.path != path]
            self._path_to_target.pop(path, None)
            self._known_files.pop(path, None)

    def targets(self) -> list[WatchTarget]:
        with self._lock:
            return list(self._targets)

    def update_target(self, path: str, **kwargs) -> None:
        """Update properties of an existing target."""
        with self._lock:
            for t in self._targets:
                if t.path == path:
                    for k, v in kwargs.items():
                        if hasattr(t, k):
                            setattr(t, k, v)
                    self._path_to_target[path] = t
                    break

    # ------------------------------------------------------------------ #
    #  Start / stop                                                         #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start watching all registered targets."""
        if self._running:
            return
        self._running = True
        self._stop_ev.clear()

        if _WATCHDOG:
            self._start_watchdog()
        else:
            self._start_polling()

        self._on_log(
            f"Watcher started ({len(self._targets)} targets, "
            f"backend={'watchdog' if _WATCHDOG else 'polling'})"
        )
        log.info("Watcher started — backend=%s", "watchdog" if _WATCHDOG else "polling")

    def stop(self) -> None:
        """Stop all watchers."""
        self._running = False
        self._stop_ev.set()
        self._debounce.stop()

        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass
            self._observer = None

        self._on_log("Watcher stopped")
        log.info("Watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def backend(self) -> str:
        return "watchdog" if _WATCHDOG else "polling"

    # ------------------------------------------------------------------ #
    #  watchdog backend                                                     #
    # ------------------------------------------------------------------ #

    def _start_watchdog(self) -> None:
        self._observer = Observer()
        for target in self._targets:
            self._mount_target(target)
        self._observer.start()

    def _mount_target(self, target: WatchTarget) -> None:
        if not _WATCHDOG or not self._observer:
            return
        handler = _WatchdogHandler(
            target=target,
            on_detected=self._debounce.push,
        )
        self._observer.schedule(handler, target.path, recursive=target.recursive)

    # ------------------------------------------------------------------ #
    #  Polling backend                                                      #
    # ------------------------------------------------------------------ #

    def _start_polling(self) -> None:
        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()

    def _poll_loop(self) -> None:
        while not self._stop_ev.is_set():
            with self._lock:
                targets = list(self._targets)

            for target in targets:
                if not target.enabled:
                    continue
                try:
                    current = self._snapshot(target.path, target.recursive)
                    known   = self._known_files.get(target.path, set())
                    new_files = current - known
                    if new_files:
                        for path in new_files:
                            self._debounce.push(path)
                    with self._lock:
                        self._known_files[target.path] = current
                except Exception as exc:
                    log.error("Watcher poll error on %s: %s", target.path, exc)

            self._stop_ev.wait(timeout=self._poll_interval)

    # ------------------------------------------------------------------ #
    #  File processing                                                      #
    # ------------------------------------------------------------------ #

    def _process_file(self, path: str) -> None:
        """Called by debounce queue when a file is stable and ready."""
        # Find the target this file belongs to
        target = self._find_target(path)
        if not target or not target.enabled:
            return

        if not Path(path).exists():
            return

        # Skip files already in the destination (avoid re-processing)
        dest = target.resolved_dest()
        if path.startswith(dest):
            return

        log.info("Watcher: processing new file %s", path)
        self._on_log(f"New file: {Path(path).name}")

        try:
            from core.scanner import FileEntry, Scanner
            from core.classifier import Classifier
            from core.heuristics import Heuristics
            from core.organizer import Organizer

            p = Path(path)
            stat = p.stat()
            entry = FileEntry(
                path=str(p),
                name=p.name,
                extension=p.suffix.lower(),
                size=stat.st_size,
                modified=stat.st_mtime,
                created=stat.st_ctime,
            )

            Classifier().classify(entry)
            Heuristics().apply(entry)

            org = Organizer(
                destination=dest,
                mode=Config.get("organize.mode", "move"),
                dry_run=False,
                conflict=Config.get("organize.handle_conflicts", "rename"),
            )
            result = org.organize([entry], source_root=target.path)

            if result.errors == 0:
                action = "moved" if Config.get("organize.mode", "move") == "move" else "copied"
                final_dest = str(Path(dest) / entry.sub_category.replace("/", os.sep)
                                 if entry.sub_category
                                 else Path(dest) / entry.category / entry.name)

                event = WatchEvent(
                    path=path,
                    dest=final_dest,
                    category=entry.category,
                    action=action,
                )
                self.files_processed += 1
                self._on_log(
                    f"  ✓ {p.name} → {entry.category}"
                    + (f"/{entry.sub_category.split('/')[-1]}" if entry.sub_category else "")
                )
                self._on_file(event)
            else:
                event = WatchEvent(path=path, dest="", category="", action="error")
                self.files_errors += 1
                self._on_log(f"  ✗ Error processing {p.name}")
                self._on_file(event)

        except Exception as exc:
            log.error("Watcher process error for %s: %s", path, exc)
            self._on_log(f"  ✗ Error: {exc}")
            self.files_errors += 1

    def _find_target(self, path: str) -> Optional[WatchTarget]:
        """Find which WatchTarget owns this file path."""
        with self._lock:
            for target in self._targets:
                if path.startswith(target.path):
                    return target
        return None

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _snapshot(folder: str, recursive: bool) -> set[str]:
        """Return set of all file paths currently in folder."""
        result = set()
        try:
            if recursive:
                for root, _, files in os.walk(folder):
                    for f in files:
                        result.add(os.path.join(root, f))
            else:
                with os.scandir(folder) as it:
                    for entry in it:
                        if entry.is_file():
                            result.add(entry.path)
        except OSError:
            pass
        return result


# ──────────────────────────────────────────────────────────────────────────────
#  watchdog event handler (only used when watchdog is installed)
# ──────────────────────────────────────────────────────────────────────────────

if _WATCHDOG:
    class _WatchdogHandler(FileSystemEventHandler):
        def __init__(self, target: WatchTarget, on_detected: Callable[[str], None]):
            super().__init__()
            self._target      = target
            self._on_detected = on_detected

        def on_created(self, event):
            if not event.is_directory:
                self._on_detected(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._on_detected(event.dest_path)
