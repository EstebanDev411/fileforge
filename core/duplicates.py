"""
core/duplicates.py
-------------------
Two-phase duplicate detection optimised for millions of files.

Phase 1 — Size grouping  (O(n), zero I/O)
    Files with unique sizes cannot be duplicates → discarded immediately.
    Only groups of 2+ files with identical size proceed to Phase 2.

Phase 2 — SHA-256 hashing  (I/O only on candidates)
    Files are read in 64 KB chunks → never loads whole file into RAM.
    Files with identical hashes are confirmed duplicates.

Resolution strategies
    move_to_folder  → moves duplicates to <destination>/_Duplicates/<hash>/
    delete          → permanently deletes duplicates (with confirmation flag)
    keep_newest     → keep file with latest mtime, remove others
    keep_oldest     → keep file with earliest mtime, remove others

Usage:
    from core.duplicates import DuplicateDetector, DuplicateGroup

    detector = DuplicateDetector()
    groups   = detector.find(entries)           # returns DuplicateGroup list
    result   = detector.resolve(groups, dest)   # applies strategy
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from system.config import Config
from system.history import History
from system.logger import get_logger

log = get_logger(__name__)

# Read files in 64 KB blocks — good balance for SSD/HDD
_CHUNK_SIZE = 65_536

ProgressCallback = Callable[[int, int, str], None]  # (done, total, current)


# ──────────────────────────────────────────────────────────────────────────────
#  Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DuplicateGroup:
    """
    A set of files that are exact byte-for-byte duplicates.

    Attributes
    ----------
    hash        : SHA-256 hex digest shared by all members
    size        : file size in bytes (same for all)
    files       : list of FileEntry objects — sorted newest → oldest
    keep_path   : path of the file to keep (set by resolver)
    """
    hash: str
    size: int
    files: list = field(default_factory=list)
    keep_path: str = ""

    @property
    def wasted_bytes(self) -> int:
        """Bytes consumed by the duplicate copies (all but one)."""
        return self.size * max(0, len(self.files) - 1)

    def wasted_mb(self) -> float:
        return self.wasted_bytes / (1024 * 1024)

    def __repr__(self) -> str:
        return (
            f"<DuplicateGroup hash={self.hash[:8]}… "
            f"files={len(self.files)} "
            f"wasted={self.wasted_mb():.2f} MB>"
        )


@dataclass
class DuplicateResult:
    """Summary of a resolve() operation."""
    groups_found: int = 0
    files_total: int = 0
    files_processed: int = 0
    files_kept: int = 0
    errors: int = 0
    bytes_freed: int = 0
    strategy: str = ""
    details: list[dict] = field(default_factory=list)

    def mb_freed(self) -> float:
        return self.bytes_freed / (1024 * 1024)

    def __str__(self) -> str:
        return (
            f"[Duplicates] Groups={self.groups_found} | "
            f"Processed={self.files_processed} | "
            f"Kept={self.files_kept} | "
            f"Freed={self.mb_freed():.1f} MB | "
            f"Errors={self.errors}"
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Detector
# ──────────────────────────────────────────────────────────────────────────────

class DuplicateDetector:
    """
    Two-phase duplicate detector.

    Parameters
    ----------
    progress_callback : callable, optional
        Called as (done, total, current_file) during hashing.
    min_size : int
        Files smaller than this (bytes) are ignored. Default from config.
    """

    def __init__(
        self,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self._progress_callback = progress_callback
        self._cancel_event = threading.Event()
        self._min_size: int = Config.get("duplicates.min_size_bytes", 1024)

    # ------------------------------------------------------------------ #
    #  Phase 1 + 2: Find duplicates                                         #
    # ------------------------------------------------------------------ #

    def find(self, entries: list) -> list[DuplicateGroup]:
        """
        Scan *entries* for duplicates and return a list of DuplicateGroup.

        Steps
        -----
        1. Group by size  — O(n), no disk I/O
        2. Discard unique sizes
        3. Hash candidates — reads only the candidate files
        4. Group by hash → confirmed duplicates
        """
        self._cancel_event.clear()

        # ── Phase 1: group by size ────────────────────────────────────
        size_groups: dict[int, list] = defaultdict(list)
        skipped_small = 0

        for entry in entries:
            if entry.size < self._min_size:
                skipped_small += 1
                continue
            size_groups[entry.size].append(entry)

        # Keep only groups with 2+ files
        candidates = [
            group for group in size_groups.values()
            if len(group) >= 2
        ]
        candidate_count = sum(len(g) for g in candidates)

        log.info(
            "Phase 1 complete: %d size groups with potential duplicates "
            "(%d candidate files, %d skipped as too small)",
            len(candidates), candidate_count, skipped_small
        )

        if not candidates:
            return []

        # ── Phase 2: hash candidates ──────────────────────────────────
        hash_groups: dict[str, list] = defaultdict(list)
        done = 0
        errors = 0

        for size_group in candidates:
            for entry in size_group:
                if self._cancel_event.is_set():
                    log.info("Duplicate detection cancelled")
                    break

                self._fire_progress(done, candidate_count, entry.path)

                file_hash = self._sha256(entry.path)
                done += 1

                if file_hash is None:
                    errors += 1
                    continue

                # Tag the entry for downstream use
                entry.duplicate_group = file_hash
                hash_groups[file_hash].append(entry)

            if self._cancel_event.is_set():
                break

        self._fire_progress(candidate_count, candidate_count, "")

        # Build DuplicateGroup objects — only confirmed duplicates
        groups: list[DuplicateGroup] = []
        for file_hash, members in hash_groups.items():
            if len(members) < 2:
                # Flag as non-duplicate (hash collision from phase 1 size match)
                for m in members:
                    m.duplicate_group = ""
                continue

            # Sort: newest first (index 0 = default keep candidate)
            members.sort(key=lambda e: e.modified, reverse=True)
            for m in members:
                m.is_duplicate = True

            group = DuplicateGroup(
                hash=file_hash,
                size=members[0].size,
                files=members,
            )
            groups.append(group)

        total_wasted = sum(g.wasted_bytes for g in groups)
        log.info(
            "Phase 2 complete: %d duplicate groups found, "
            "%.1f MB wasted, %d hash errors",
            len(groups), total_wasted / (1024 * 1024), errors
        )

        return groups

    # ------------------------------------------------------------------ #
    #  Resolution                                                           #
    # ------------------------------------------------------------------ #

    def resolve(
        self,
        groups: list[DuplicateGroup],
        destination: Optional[str | Path] = None,
        strategy: Optional[str] = None,
        keep: Optional[str] = None,
        confirmed: bool = False,
    ) -> DuplicateResult:
        """
        Apply a resolution strategy to the detected duplicate groups.

        Parameters
        ----------
        groups : list[DuplicateGroup]
            Output of find().
        destination : str | Path
            Base folder used by 'move_to_folder' strategy.
        strategy : str
            'move_to_folder' | 'delete'
            Default: from config.duplicates.strategy
        keep : str
            'newest' | 'oldest'
            Default: from config.duplicates.keep
        confirmed : bool
            Must be True to execute 'delete' strategy.
            Safety guard against accidental deletion.

        Returns
        -------
        DuplicateResult
        """
        strategy = strategy or Config.get("duplicates.strategy", "move_to_folder")
        keep     = keep     or Config.get("duplicates.keep", "newest")

        if strategy == "delete" and not confirmed:
            raise RuntimeError(
                "Delete strategy requires confirmed=True. "
                "Set confirmed=True explicitly to allow permanent deletion."
            )

        result = DuplicateResult(
            groups_found=len(groups),
            files_total=sum(len(g.files) for g in groups),
            strategy=strategy,
        )

        # Resolve destination folder for move strategy
        dup_folder_name = Config.get("duplicates.duplicates_folder", "_Duplicates")
        if destination:
            dup_root = Path(destination) / dup_folder_name
        else:
            dup_root = Path(dup_folder_name)

        log.info(
            "Resolving %d duplicate groups [strategy=%s, keep=%s]",
            len(groups), strategy, keep
        )

        for group in groups:
            if self._cancel_event.is_set():
                break

            # Determine which file to keep
            keeper = self._select_keeper(group, keep)
            group.keep_path = keeper.path
            result.files_kept += 1

            # Process the rest
            duplicates_to_handle = [f for f in group.files if f.path != keeper.path]

            for dup in duplicates_to_handle:
                if self._cancel_event.is_set():
                    break
                detail = {"hash": group.hash[:12], "kept": keeper.path, "duplicate": dup.path}

                try:
                    if strategy == "move_to_folder":
                        dest = dup_root / group.hash[:16] / dup.name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest = self._safe_dest(dup.path, dest)
                        shutil.move(dup.path, str(dest))
                        detail["action"] = f"moved_to:{dest}"
                        result.bytes_freed += dup.size

                    elif strategy == "delete":
                        os.remove(dup.path)
                        detail["action"] = "deleted"
                        result.bytes_freed += dup.size

                    result.files_processed += 1

                except PermissionError as exc:
                    log.warning("Permission denied resolving duplicate %s: %s", dup.path, exc)
                    detail["action"] = f"error:{exc}"
                    result.errors += 1
                except OSError as exc:
                    log.error("Error resolving duplicate %s: %s", dup.path, exc)
                    detail["action"] = f"error:{exc}"
                    result.errors += 1

                result.details.append(detail)

        # Persist to history
        if Config.get("history.enabled", True):
            History.record(
                action="duplicate",
                source="",
                destination=str(dup_root) if strategy == "move_to_folder" else "",
                files_affected=result.files_processed,
                errors=result.errors,
                details=result.details,
            )

        log.info(str(result))
        return result

    def cancel(self) -> None:
        """Cancel an in-progress find() or resolve() operation."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------ #
    #  Hashing                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sha256(path: str) -> Optional[str]:
        """
        Compute SHA-256 of a file using 64 KB read blocks.
        Returns hex digest or None on error.
        """
        h = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                while chunk := fh.read(_CHUNK_SIZE):
                    h.update(chunk)
            return h.hexdigest()
        except PermissionError:
            log.warning("Permission denied hashing: %s", path)
        except OSError as exc:
            log.warning("Hash error for %s: %s", path, exc)
        return None

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _select_keeper(group: DuplicateGroup, keep: str):
        """Return the FileEntry that should be kept from a group."""
        if keep == "oldest":
            return min(group.files, key=lambda e: e.modified)
        # Default: newest
        return max(group.files, key=lambda e: e.modified)

    @staticmethod
    def _safe_dest(src: str, dest: Path) -> Path:
        """Avoid overwriting in the duplicates folder — append counter if needed."""
        if not dest.exists():
            return dest
        stem, suffix, parent = dest.stem, dest.suffix, dest.parent
        i = 1
        while True:
            candidate = parent / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate
            i += 1

    def _fire_progress(self, done: int, total: int, current: str) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(done, total, current)
            except Exception:
                pass
