"""Asyncio worker pool consuming tasks from a :class:`TaskScheduler`.

Contract: submit all tasks first, then call :meth:`run`.  The pool applies a
per-task timeout, isolates task failures, and supports cancellation of both
queued and in-flight work.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from core.constants import TaskState
from core.exceptions import TaskTimeoutError
from core.logger import get_logger
from core.scheduler import Task, TaskScheduler

_log = get_logger(__name__)


@dataclass(slots=True)
class PoolStats:
    """Summary of a completed pool run."""

    submitted: int = 0
    done: int = 0
    failed: int = 0
    cancelled: int = 0
    duration: float = 0.0


class WorkerPool:
    """Executes scheduler tasks with bounded concurrency."""

    def __init__(
        self,
        scheduler: TaskScheduler,
        *,
        concurrency: int = 8,
        default_timeout: float | None = 30.0,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self._scheduler = scheduler
        self._concurrency = concurrency
        self._default_timeout = default_timeout
        self._workers: list[asyncio.Task[None]] = []
        self._in_flight = 0
        self._peak_in_flight = 0

    @property
    def peak_in_flight(self) -> int:
        """Highest number of concurrently executing tasks observed."""
        return self._peak_in_flight

    async def run(self) -> PoolStats:
        """Run all queued tasks; returns a summary of outcomes."""
        started = time.monotonic()
        for _ in range(self._concurrency):
            self._scheduler.put_sentinel()
        self._workers = [
            asyncio.create_task(self._worker(idx), name=f"ix-worker-{idx}")
            for idx in range(self._concurrency)
        ]
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        counts = self._scheduler.counts()
        return PoolStats(
            submitted=self._scheduler.submitted,
            done=counts.get(TaskState.DONE, 0),
            failed=counts.get(TaskState.FAILED, 0),
            cancelled=counts.get(TaskState.CANCELLED, 0),
            duration=time.monotonic() - started,
        )

    async def cancel(self) -> None:
        """Cancel in-flight workers and drain queued tasks."""
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers = []
        self._scheduler.cancel_pending()

    async def _worker(self, index: int) -> None:
        while True:
            task = await self._scheduler.next_task()
            if task is None:
                return
            await self._execute(task, index)

    async def _execute(self, task: Task, index: int) -> None:
        self._scheduler.mark_running(task)
        self._in_flight += 1
        self._peak_in_flight = max(self._peak_in_flight, self._in_flight)
        timeout = task.timeout if task.timeout is not None else self._default_timeout
        _log.debug("worker %s started task %s", index, task.id)
        try:
            if task.coro is None:
                raise TaskTimeoutError(f"task {task.id!r} has no coroutine")
            if timeout is None:
                result = await task.coro
            else:
                result = await asyncio.wait_for(task.coro, timeout=timeout)
        except TimeoutError:
            error = TaskTimeoutError(f"task {task.id!r} timed out after {timeout}s")
            self._scheduler.mark_failed(task, error)
            _log.warning("task %s timed out after %ss", task.id, timeout)
        except asyncio.CancelledError:
            self._scheduler.mark_cancelled(task)
            raise
        except Exception as exc:
            self._scheduler.mark_failed(task, exc)
            _log.warning("task %s failed: %s", task.id, exc)
        else:
            self._scheduler.mark_done(task, result)
            _log.debug("worker %s finished task %s", index, task.id)
        finally:
            self._in_flight -= 1
