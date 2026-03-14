"""
core/scheduler.py
------------------
Task scheduler for FileForge — runs Auto Organize on a schedule.

Schedules are stored in config/schedules.json and persist across restarts.

Supported intervals
-------------------
  minutes   — every N minutes  (min: 5)
  hourly    — every N hours
  daily     — every day at HH:MM
  weekly    — every weekday (mon-sun) at HH:MM
  on_startup — once when the app starts

Usage
-----
    from core.scheduler import Scheduler, Schedule

    scheduler = Scheduler(on_run=my_callback, on_log=print)

    task = Schedule(
        name="Daily Downloads cleanup",
        path="C:/Users/John/Downloads",
        destination="C:/Organized",
        interval="daily",
        at_time="02:00",
        enabled=True,
    )
    scheduler.add(task)
    scheduler.start()
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from system.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Schedule:
    """One scheduled task."""
    id:          str   = field(default_factory=lambda: str(uuid.uuid4()))
    name:        str   = "Untitled schedule"
    path:        str   = ""           # source folder to organize
    destination: str   = ""           # empty = <path>/_Organized
    interval:    str   = "daily"      # minutes | hourly | daily | weekly | on_startup
    every_n:     int   = 1            # used by minutes/hourly
    at_time:     str   = "02:00"      # HH:MM — used by daily/weekly
    weekday:     int   = 0            # 0=Mon … 6=Sun — used by weekly
    enabled:     bool  = True
    dry_run:     bool  = False

    last_run:    str   = ""           # ISO timestamp of last execution
    next_run:    str   = ""           # ISO timestamp of next scheduled run
    run_count:   int   = 0
    last_status: str   = ""           # "ok" | "error" | "running"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "Schedule":
        s = cls()
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s

    def resolved_dest(self) -> str:
        if self.destination.strip():
            return self.destination
        from system.config import Config
        name = Config.get("organize.output_folder_name", "_Organized")
        return str(Path(self.path) / name)

    def compute_next_run(self, from_dt: Optional[datetime] = None) -> datetime:
        """Calculate the next scheduled datetime from now (or from_dt)."""
        now = from_dt or datetime.now()

        if self.interval == "on_startup":
            return now

        if self.interval == "minutes":
            return now + timedelta(minutes=max(self.every_n, 5))

        if self.interval == "hourly":
            return now + timedelta(hours=max(self.every_n, 1))

        if self.interval == "daily":
            h, m = self._parse_time(self.at_time)
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        if self.interval == "weekly":
            h, m = self._parse_time(self.at_time)
            days_ahead = (self.weekday - now.weekday()) % 7
            candidate = (now + timedelta(days=days_ahead)).replace(
                hour=h, minute=m, second=0, microsecond=0
            )
            if candidate <= now:
                candidate += timedelta(weeks=1)
            return candidate

        return now + timedelta(hours=1)

    @staticmethod
    def _parse_time(t: str) -> tuple[int, int]:
        try:
            parts = t.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 2, 0

    def is_due(self) -> bool:
        """Return True if this schedule should run now."""
        if not self.enabled or not self.path:
            return False
        if self.interval == "on_startup":
            return self.run_count == 0
        if not self.next_run:
            return True
        try:
            return datetime.now() >= datetime.fromisoformat(self.next_run)
        except ValueError:
            return True


# ──────────────────────────────────────────────────────────────────────────────
#  Storage path
# ──────────────────────────────────────────────────────────────────────────────

def _schedules_path() -> Path:
    try:
        from paths import Paths
        p = Paths.writable_root() / "config" / "schedules.json"
    except ImportError:
        p = Path(__file__).parent.parent / "config" / "schedules.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ──────────────────────────────────────────────────────────────────────────────
#  Scheduler
# ──────────────────────────────────────────────────────────────────────────────

class Scheduler:
    """
    Runs Auto Organize tasks on a configurable schedule.

    Parameters
    ----------
    on_run : callable(Schedule, result_dict)
        Called after each task completes.
    on_log : callable(str)
        Called with status messages.
    tick_interval : int
        Seconds between schedule checks. Default: 30.
    """

    def __init__(
        self,
        on_run:        Optional[Callable] = None,
        on_log:        Optional[Callable] = None,
        tick_interval: int = 30,
    ):
        self._on_run       = on_run  or (lambda s, r: None)
        self._on_log       = on_log  or log.info
        self._tick         = tick_interval
        self._schedules:   list[Schedule] = []
        self._running      = False
        self._stop_ev      = threading.Event()
        self._lock         = threading.Lock()
        self._active_tasks: set[str] = set()   # ids of currently running tasks
        self.load()

    # ------------------------------------------------------------------ #
    #  Persistence                                                          #
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        path = _schedules_path()
        if not path.exists():
            self._schedules = []
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._schedules = [Schedule.from_dict(d) for d in data.get("schedules", [])]
            log.info("Scheduler: loaded %d schedules", len(self._schedules))
        except Exception as exc:
            log.error("Scheduler: failed to load: %s", exc)
            self._schedules = []

    def save(self) -> None:
        path = _schedules_path()
        with self._lock:
            data = {"schedules": [s.to_dict() for s in self._schedules]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    def reload(self) -> None:
        self.load()

    # ------------------------------------------------------------------ #
    #  Schedule management                                                  #
    # ------------------------------------------------------------------ #

    def add(self, schedule: Schedule) -> None:
        if not schedule.id:
            schedule.id = str(uuid.uuid4())
        # Set next_run immediately
        schedule.next_run = schedule.compute_next_run().isoformat()
        with self._lock:
            self._schedules.append(schedule)
        log.info("Scheduler: added '%s' [%s]", schedule.name, schedule.interval)

    def remove(self, schedule_id: str) -> bool:
        with self._lock:
            before = len(self._schedules)
            self._schedules = [s for s in self._schedules if s.id != schedule_id]
            removed = len(self._schedules) < before
        if removed:
            self.save()
        return removed

    def update(self, schedule: Schedule) -> None:
        with self._lock:
            for i, s in enumerate(self._schedules):
                if s.id == schedule.id:
                    self._schedules[i] = schedule
                    return
            self._schedules.append(schedule)

    def get(self, schedule_id: str) -> Optional[Schedule]:
        with self._lock:
            for s in self._schedules:
                if s.id == schedule_id:
                    return s
        return None

    def all_schedules(self) -> list[Schedule]:
        with self._lock:
            return list(self._schedules)

    def run_now(self, schedule_id: str) -> None:
        """Trigger a schedule immediately regardless of its next_run time."""
        s = self.get(schedule_id)
        if s:
            thread = threading.Thread(
                target=self._execute, args=(s,), daemon=True
            )
            thread.start()

    # ------------------------------------------------------------------ #
    #  Start / stop                                                         #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_ev.clear()
        thread = threading.Thread(target=self._tick_loop, daemon=True, name="ff_scheduler")
        thread.start()
        self._on_log(f"Scheduler started ({len(self._schedules)} schedules)")
        log.info("Scheduler started")

    def stop(self) -> None:
        self._running = False
        self._stop_ev.set()
        self._on_log("Scheduler stopped")
        log.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------ #
    #  Tick loop                                                            #
    # ------------------------------------------------------------------ #

    def _tick_loop(self) -> None:
        while not self._stop_ev.is_set():
            self._check_due()
            self._stop_ev.wait(timeout=self._tick)

    def _check_due(self) -> None:
        with self._lock:
            due = [s for s in self._schedules
                   if s.is_due() and s.id not in self._active_tasks]

        for schedule in due:
            thread = threading.Thread(
                target=self._execute, args=(schedule,), daemon=True,
                name=f"ff_sched_{schedule.id[:8]}"
            )
            thread.start()

    # ------------------------------------------------------------------ #
    #  Task execution                                                       #
    # ------------------------------------------------------------------ #

    def _execute(self, schedule: Schedule) -> None:
        with self._lock:
            self._active_tasks.add(schedule.id)
            schedule.last_status = "running"

        start_time = datetime.now()
        self._on_log(f"▶ Running: {schedule.name}")
        log.info("Scheduler: executing '%s'", schedule.name)

        result = {"organized": 0, "errors": 0, "duration_s": 0.0}

        try:
            from core.scanner import Scanner
            from core.classifier import Classifier
            from core.heuristics import Heuristics
            from core.rules import RulesEngine
            from core.duplicates import DuplicateDetector
            from core.organizer import Organizer
            from system.config import Config

            # Scan
            self._on_log(f"  Scanning: {schedule.path}")
            scanner = Scanner(progress_interval=2000)
            entries = scanner.scan(schedule.path)
            self._on_log(f"  {len(entries):,} files found")

            if entries:
                # Rules → Classify → Heuristics
                RulesEngine().apply_all(entries)
                Classifier().classify_all(entries)
                Heuristics().apply_all(entries)

                # Duplicates (if enabled)
                dup_groups = []
                if Config.get("duplicates.enabled", True):
                    det = DuplicateDetector()
                    dup_groups = det.find(entries)

                # Filter skip entries
                to_organize = [e for e in entries
                                if getattr(e, "sub_category", "") != "__SKIP__"]

                # Organize
                org = Organizer(
                    destination=schedule.resolved_dest(),
                    dry_run=schedule.dry_run,
                    mode=Config.get("organize.mode", "move"),
                )
                org_result = org.organize(to_organize, source_root=schedule.path)

                # Resolve dupes
                if dup_groups and not schedule.dry_run:
                    det.resolve(
                        dup_groups,
                        destination=schedule.resolved_dest(),
                        strategy=Config.get("duplicates.strategy", "move_to_folder"),
                        keep=Config.get("duplicates.keep", "newest"),
                        confirmed=True,
                    )

                result["organized"] = org_result.moved + org_result.copied
                result["errors"]    = org_result.errors

        except Exception as exc:
            log.error("Scheduler task error '%s': %s", schedule.name, exc)
            result["errors"] += 1
            schedule.last_status = "error"
        else:
            schedule.last_status = "ok"

        duration = (datetime.now() - start_time).total_seconds()
        result["duration_s"] = duration

        # Update schedule state
        with self._lock:
            schedule.last_run  = start_time.isoformat(timespec="seconds")
            schedule.next_run  = schedule.compute_next_run().isoformat()
            schedule.run_count += 1
            self._active_tasks.discard(schedule.id)
            # Inline update — avoid calling self.update() while lock is held
            for i, s in enumerate(self._schedules):
                if s.id == schedule.id:
                    self._schedules[i] = schedule
                    break
            else:
                self._schedules.append(schedule)

        self.save()

        status = "✓" if schedule.last_status == "ok" else "✗"
        self._on_log(
            f"  {status} Done: {result['organized']:,} files organized "
            f"in {duration:.1f}s"
        )
        self._on_run(schedule, result)
        log.info(
            "Scheduler: '%s' complete — %d organized, %d errors, %.1fs",
            schedule.name, result["organized"], result["errors"], duration,
        )
