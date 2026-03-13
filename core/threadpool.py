"""
core/threadpool.py
-------------------
Centralised ThreadPoolExecutor wrapper with:
  - Adaptive worker count (cpu_count based)
  - Safe cancellation via threading.Event
  - Thread-safe progress queue
  - Batch submission with per-task error isolation
  - Context manager support

Usage:
    from core.threadpool import ThreadPool

    pool = ThreadPool(max_workers=8)

    with pool:
        futures = pool.submit_batch(my_func, items)
        for result in pool.iter_results(futures):
            print(result)

    # Or as a one-shot call:
    results, errors = ThreadPool.run_batch(my_func, items, max_workers=4)
"""

from __future__ import annotations

import os
import queue
import threading
from concurrent.futures import (
    ThreadPoolExecutor, Future, as_completed, wait, FIRST_COMPLETED
)
from typing import Any, Callable, Iterable, Iterator, Optional

from system.config import Config
from system.logger import get_logger

log = get_logger(__name__)


class ThreadPool:
    """
    Managed thread pool with cancellation and progress support.

    Parameters
    ----------
    max_workers : int
        Number of worker threads. 0 = auto (cpu_count * 2, capped at 16).
    cancel_event : threading.Event, optional
        Shared cancellation flag. Workers check this between tasks.
    """

    _MAX_AUTO_WORKERS = 16

    def __init__(
        self,
        max_workers: int = 0,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        self._cancel_event = cancel_event or threading.Event()
        self._max_workers  = self._resolve_workers(max_workers)
        self._executor: Optional[ThreadPoolExecutor] = None
        self._progress_q: queue.Queue = queue.Queue()
        self._submitted  = 0
        self._completed  = 0
        self._lock       = threading.Lock()

        log.debug("ThreadPool init: workers=%d", self._max_workers)

    # ------------------------------------------------------------------ #
    #  Context manager                                                      #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "ThreadPool":
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="ff_worker",
        )
        return self

    def __exit__(self, *_) -> None:
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=self.is_cancelled)
            self._executor = None

    # ------------------------------------------------------------------ #
    #  Submission                                                           #
    # ------------------------------------------------------------------ #

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit a single task. Returns a Future."""
        if not self._executor:
            raise RuntimeError("ThreadPool must be used as a context manager.")
        with self._lock:
            self._submitted += 1
        return self._executor.submit(self._safe_run, fn, args, kwargs)

    def submit_batch(
        self,
        fn: Callable,
        items: Iterable,
        *,
        extra_args: tuple = (),
    ) -> list[Future]:
        """
        Submit fn(item, *extra_args) for every item.
        Returns list of Futures in submission order.
        """
        futures = []
        for item in items:
            if self._cancel_event.is_set():
                break
            futures.append(self.submit(fn, item, *extra_args))
        return futures

    # ------------------------------------------------------------------ #
    #  Result iteration                                                     #
    # ------------------------------------------------------------------ #

    def iter_results(
        self,
        futures: list[Future],
        *,
        timeout: Optional[float] = None,
    ) -> Iterator[Any]:
        """
        Yield results as futures complete (order not guaranteed).
        Skips futures that raised exceptions (logs them).
        Stops early if cancel() is called.
        """
        for future in as_completed(futures, timeout=timeout):
            if self._cancel_event.is_set():
                break
            try:
                result = future.result()
                with self._lock:
                    self._completed += 1
                if result is not _TASK_ERROR:
                    yield result
            except Exception as exc:
                log.error("Worker result error: %s", exc)

    # ------------------------------------------------------------------ #
    #  Cancellation                                                         #
    # ------------------------------------------------------------------ #

    def cancel(self) -> None:
        """Signal all workers to stop after their current task."""
        self._cancel_event.set()
        log.info("ThreadPool cancellation requested")

    def reset_cancel(self) -> None:
        """Clear the cancel flag so the pool can be reused."""
        self._cancel_event.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ------------------------------------------------------------------ #
    #  Progress                                                             #
    # ------------------------------------------------------------------ #

    def report_progress(self, value: Any) -> None:
        """Workers call this to push progress updates to the main thread."""
        self._progress_q.put_nowait(value)

    def drain_progress(self) -> list:
        """Main thread calls this to collect all pending progress updates."""
        items = []
        try:
            while True:
                items.append(self._progress_q.get_nowait())
        except queue.Empty:
            pass
        return items

    # ------------------------------------------------------------------ #
    #  Stats                                                                #
    # ------------------------------------------------------------------ #

    @property
    def submitted(self) -> int:
        return self._submitted

    @property
    def completed(self) -> int:
        return self._completed

    @property
    def max_workers(self) -> int:
        return self._max_workers

    # ------------------------------------------------------------------ #
    #  Class-level convenience                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def run_batch(
        cls,
        fn: Callable,
        items: Iterable,
        *,
        max_workers: int = 0,
        extra_args: tuple = (),
    ) -> tuple[list, list[str]]:
        """
        One-shot: run fn(item, *extra_args) for all items, collect results.

        Returns
        -------
        (results, errors)
            results : list of successful return values
            errors  : list of error strings
        """
        results: list = []
        errors:  list[str] = []

        with cls(max_workers=max_workers) as pool:
            futures = pool.submit_batch(fn, items, extra_args=extra_args)
            for future in as_completed(futures):
                try:
                    val = future.result()
                    if isinstance(val, _TaskError):
                        errors.append("task failed (see log)")
                    else:
                        results.append(val)
                except Exception as exc:
                    errors.append(str(exc))

        return results, errors

    # ------------------------------------------------------------------ #
    #  Internal                                                             #
    # ------------------------------------------------------------------ #

    def _safe_run(self, fn: Callable, args: tuple, kwargs: dict) -> Any:
        """
        Wrapper that catches all exceptions per-task so one failing
        task never kills the whole pool.
        """
        if self._cancel_event.is_set():
            return _TASK_ERROR
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            log.error("Task %s raised: %s", fn.__name__, exc)
            return _TASK_ERROR

    @classmethod
    def _resolve_workers(cls, requested: int) -> int:
        """Resolve 0 → auto based on CPU count and config."""
        if requested > 0:
            return requested
        cfg = Config.get("scan.max_workers", 0)
        if cfg > 0:
            return int(cfg)
        cpu = os.cpu_count() or 2
        auto = min(cpu * 2, cls._MAX_AUTO_WORKERS)
        return max(auto, 2)


# Sentinel — returned by _safe_run when a task fails
class _TaskError:
    pass

_TASK_ERROR = _TaskError()

