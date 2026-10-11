"""Run blocking callables off the event loop (Phase 25, S25.4).

Pure-CPU or blocking-IO work (PDF/EXIF parsing, ``json`` reads, etc.) must not
run on the event loop or it stalls every concurrent task.  :class:`OffloadPool`
wraps a *bounded* :class:`~concurrent.futures.ThreadPoolExecutor` so callers can
``await pool.run(func, ...)`` without spawning an unbounded number of threads.

:func:`offload` is a process-wide convenience for callers that do not carry a
per-scan pool (e.g. scripts); modules normally use ``ctx.to_thread(...)``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any, TypeVar

from core.logger import get_logger

T = TypeVar("T")

_log = get_logger(__name__)

DEFAULT_WORKERS = 4


@dataclass(slots=True)
class OffloadStats:
    """Counters describing how much work has been handed to the threads."""

    submitted: int = 0
    completed: int = 0


class OffloadPool:
    """Bounded thread pool that runs blocking callables off the event loop."""

    def __init__(
        self,
        max_workers: int = DEFAULT_WORKERS,
        *,
        thread_name_prefix: str = "ix-offload",
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = max_workers
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=thread_name_prefix
        )
        self._stats = OffloadStats()

    @property
    def max_workers(self) -> int:
        """Maximum number of worker threads."""
        return self._max_workers

    @property
    def stats(self) -> OffloadStats:
        """Snapshot of submitted/completed counters."""
        return OffloadStats(
            submitted=self._stats.submitted,
            completed=self._stats.completed,
        )

    async def run(self, func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        """Run ``func(*args, **kwargs)`` in a worker thread and await it."""
        loop = asyncio.get_running_loop()
        self._stats.submitted += 1
        try:
            return await loop.run_in_executor(
                self._pool, partial(func, *args, **kwargs)
            )
        finally:
            self._stats.completed += 1

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting work and tear the pool down."""
        self._pool.shutdown(wait=wait)

    async def aclose(self) -> None:
        """Shut the pool down without blocking the event loop."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._pool.shutdown, True)


_default_pool: OffloadPool | None = None


def configure_offload(max_workers: int = DEFAULT_WORKERS) -> None:
    """(Re)create the process-wide pool with ``max_workers`` threads."""
    global _default_pool
    if _default_pool is not None:
        _default_pool.shutdown(wait=False)
    _default_pool = OffloadPool(max_workers, thread_name_prefix="ix-offload-shared")


def get_offload_pool() -> OffloadPool:
    """Return the lazily-created process-wide pool."""
    global _default_pool
    if _default_pool is None:
        _default_pool = OffloadPool()
    return _default_pool


async def offload[T](func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a blocking callable in the shared pool and await its result."""
    return await get_offload_pool().run(func, *args, **kwargs)


async def shutdown_offload() -> None:
    """Tear the process-wide pool down (used by scripts and tests)."""
    global _default_pool
    if _default_pool is not None:
        await _default_pool.aclose()
        _default_pool = None


__all__ = [
    "DEFAULT_WORKERS",
    "OffloadPool",
    "OffloadStats",
    "configure_offload",
    "get_offload_pool",
    "offload",
    "shutdown_offload",
]
