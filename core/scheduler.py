"""Priority task queue with per-task state tracking.

Lower ``priority`` values run first; equal priorities run FIFO.
The pool consumes tasks via :meth:`next_task` and reports outcomes back
through the ``mark_*`` methods so counts stay consistent.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from itertools import count
from typing import Any

from core.constants import TaskState
from core.exceptions import ScanCancelledError

_SENTINEL_PRIORITY = 2**31 - 1
_Coroutine = Coroutine[Any, Any, Any]


@dataclass(slots=True)
class Task:
    """A unit of work submitted to the scheduler."""

    id: str
    name: str
    coro: _Coroutine | None
    priority: int = 0
    state: TaskState = TaskState.PENDING
    result: Any = None
    error: BaseException | None = None
    timeout: float | None = None
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration(self) -> float | None:
        """Seconds from start to finish, or ``None`` if not finished."""
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def close(self) -> None:
        """Close an unstarted coroutine so it is never leaked."""
        if self.coro is not None:
            self.coro.close()
            self.coro = None


class TaskScheduler:
    """FIFO/priority scheduler with status accounting."""

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, int, Task | None]] = (
            asyncio.PriorityQueue()
        )
        self._seq = count()
        self._tasks: dict[str, Task] = {}
        self._counts: dict[TaskState, int] = {state: 0 for state in TaskState}
        self._submitted = 0

    def submit(
        self,
        coro: _Coroutine,
        *,
        name: str = "task",
        priority: int = 0,
        timeout: float | None = None,
        task_id: str | None = None,
    ) -> Task:
        """Queue a coroutine for execution."""
        tid = task_id or f"{name}-{next(self._seq):04d}"
        task = Task(id=tid, name=name, coro=coro, priority=priority, timeout=timeout)
        self._tasks[tid] = task
        self._submitted += 1
        self._counts[TaskState.PENDING] += 1
        self._queue.put_nowait((priority, next(self._seq), task))
        return task

    async def next_task(self) -> Task | None:
        """Block until the next real task is available.

        Returns ``None`` when a worker sentinel is popped (worker should
        exit).
        """
        while True:
            _priority, _seq, item = await self._queue.get()
            if item is None:
                return None
            return item

    def put_sentinel(self) -> None:
        """Insert a worker exit marker (lowest possible priority)."""
        self._queue.put_nowait((_SENTINEL_PRIORITY, next(self._seq), None))

    def mark_running(self, task: Task) -> None:
        """Transition a task to RUNNING."""
        self._transition(task, TaskState.RUNNING)
        task.started_at = time.monotonic()

    def mark_done(self, task: Task, result: Any) -> None:
        """Transition a task to DONE with its result."""
        self._transition(task, TaskState.DONE)
        task.result = result
        task.finished_at = time.monotonic()
        task.close()

    def mark_failed(self, task: Task, error: BaseException) -> None:
        """Transition a task to FAILED with its exception."""
        self._transition(task, TaskState.FAILED)
        task.error = error
        task.finished_at = time.monotonic()
        task.close()

    def mark_cancelled(self, task: Task) -> None:
        """Transition a task to CANCELLED."""
        self._transition(task, TaskState.CANCELLED)
        task.error = ScanCancelledError(f"task {task.name!r} cancelled")
        task.finished_at = time.monotonic()
        task.close()

    def cancel_pending(self) -> int:
        """Cancel every queued task; returns how many were cancelled."""
        cancelled = 0
        while True:
            try:
                _priority, _seq, item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                continue
            if item.state is TaskState.PENDING:
                self.mark_cancelled(item)
                cancelled += 1
        return cancelled

    def close_all(self) -> int:
        """Close every unfinished coroutine (cleanup); returns count."""
        closed = 0
        for task in self._tasks.values():
            if task.coro is not None:
                task.close()
                closed += 1
        return closed

    def counts(self) -> dict[TaskState, int]:
        """Snapshot of task counts per state."""
        return dict(self._counts)

    @property
    def submitted(self) -> int:
        """Total tasks ever submitted."""
        return self._submitted

    @property
    def pending_count(self) -> int:
        """Tasks submitted but not yet finished."""
        return self._submitted - sum(
            self._counts[s]
            for s in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED)
        )

    @property
    def tasks(self) -> list[Task]:
        """All tasks in submission order."""
        return list(self._tasks.values())

    def get(self, task_id: str) -> Task | None:
        """Look up a task by id."""
        return self._tasks.get(task_id)

    def _transition(self, task: Task, new_state: TaskState) -> None:
        if task.state in (TaskState.DONE, TaskState.FAILED, TaskState.CANCELLED):
            raise ValueError(f"task {task.id!r} already finished as {task.state.value}")
        self._counts[task.state] -= 1
        task.state = new_state
        self._counts[new_state] += 1
