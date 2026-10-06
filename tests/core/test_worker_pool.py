"""Worker pool tests: concurrency, isolation, timeout, cancellation."""

import asyncio
from typing import Any

from core.constants import TaskState
from core.exceptions import TaskTimeoutError
from core.scheduler import TaskScheduler
from core.worker_pool import WorkerPool


async def _value(v: Any) -> Any:
    return v


async def _boom() -> None:
    raise ValueError("task exploded")


async def _sleep_then(seconds: float, store: dict[str, Any], key: str) -> str:
    await asyncio.sleep(seconds)
    store[key] = True
    return key


async def test_collects_results() -> None:
    sched = TaskScheduler()
    store: dict[str, Any] = {}
    for i in range(5):
        sched.submit(_sleep_then(0.01, store, f"k{i}"), name=f"t{i}")
    pool = WorkerPool(sched, concurrency=3, default_timeout=5.0)
    stats = await pool.run()
    assert stats.submitted == 5
    assert stats.done == 5
    assert stats.failed == 0
    assert len(store) == 5


async def test_failure_isolation() -> None:
    sched = TaskScheduler()
    store: dict[str, Any] = {}
    sched.submit(_boom(), name="bad")
    for i in range(3):
        sched.submit(_sleep_then(0.01, store, f"ok{i}"), name=f"good{i}")
    pool = WorkerPool(sched, concurrency=4, default_timeout=5.0)
    stats = await pool.run()
    assert stats.failed == 1
    assert stats.done == 3
    assert len(store) == 3
    failed = [t for t in sched.tasks if t.state is TaskState.FAILED]
    assert len(failed) == 1
    assert isinstance(failed[0].error, ValueError)


async def test_timeout_marks_task_failed() -> None:
    sched = TaskScheduler()
    task = sched.submit(asyncio.sleep(5), name="slow", timeout=0.05)
    pool = WorkerPool(sched, concurrency=1, default_timeout=5.0)
    stats = await pool.run()
    assert stats.failed == 1
    assert task.state is TaskState.FAILED
    assert isinstance(task.error, TaskTimeoutError)


async def test_default_timeout_applies() -> None:
    sched = TaskScheduler()
    task = sched.submit(asyncio.sleep(5), name="slow")
    pool = WorkerPool(sched, concurrency=1, default_timeout=0.05)
    await pool.run()
    assert isinstance(task.error, TaskTimeoutError)


async def test_concurrency_limit_respected() -> None:
    sched = TaskScheduler()
    state = {"current": 0, "peak": 0}

    async def workload() -> None:
        state["current"] += 1
        state["peak"] = max(state["peak"], state["current"])
        await asyncio.sleep(0.02)
        state["current"] -= 1

    for _ in range(8):
        sched.submit(workload(), name="w")
    pool = WorkerPool(sched, concurrency=2, default_timeout=5.0)
    await pool.run()
    assert state["peak"] <= 2
    assert state["current"] == 0


async def test_cancellation_drains_everything() -> None:
    sched = TaskScheduler()
    tasks = [sched.submit(asyncio.sleep(30), name=f"long{i}") for i in range(4)]
    pool = WorkerPool(sched, concurrency=2, default_timeout=None)

    runner = asyncio.create_task(pool.run())
    await asyncio.sleep(0.05)  # let workers start tasks
    await pool.cancel()
    await asyncio.wait_for(runner, timeout=2.0)

    for task in tasks:
        assert task.state in (TaskState.CANCELLED, TaskState.PENDING)
    counts = sched.counts()
    assert counts[TaskState.CANCELLED] == 4
    assert counts[TaskState.RUNNING] == 0


async def test_empty_queue_completes() -> None:
    sched = TaskScheduler()
    pool = WorkerPool(sched, concurrency=2)
    stats = await pool.run()
    assert stats.submitted == 0
    assert stats.duration >= 0.0


async def test_peak_in_flight_metric() -> None:
    sched = TaskScheduler()

    async def burst() -> str:
        await asyncio.sleep(0.02)
        return "x"

    for _ in range(6):
        sched.submit(burst(), name="b")
    pool = WorkerPool(sched, concurrency=3, default_timeout=5.0)
    await pool.run()
    assert 1 <= pool.peak_in_flight <= 3
