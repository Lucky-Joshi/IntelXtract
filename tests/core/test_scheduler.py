"""Task scheduler tests."""

from typing import Any

import pytest

from core.constants import TaskState
from core.exceptions import ScanCancelledError
from core.scheduler import Task, TaskScheduler


async def _value(v: Any) -> Any:
    return v


async def test_fifo_within_same_priority() -> None:
    sched = TaskScheduler()
    tasks = [sched.submit(_value(i), name=f"t{i}") for i in range(5)]
    order: list[str] = []
    for _ in range(5):
        task = await sched.next_task()
        assert task is not None
        order.append(task.name)
    assert order == [t.name for t in tasks]
    assert sched.close_all() == 5


async def test_priority_order() -> None:
    sched = TaskScheduler()
    sched.submit(_value(1), name="low", priority=10)
    sched.submit(_value(2), name="high", priority=1)
    sched.submit(_value(3), name="mid", priority=5)
    order = []
    for _ in range(3):
        task = await sched.next_task()
        assert task is not None
        order.append(task.name)
    assert order == ["high", "mid", "low"]
    assert sched.close_all() == 3


async def test_sentinel_returns_none() -> None:
    sched = TaskScheduler()
    sched.put_sentinel()
    assert await sched.next_task() is None


async def test_sentinel_is_last() -> None:
    sched = TaskScheduler()
    sched.put_sentinel()
    sched.submit(_value(1), name="real", priority=0)
    first = await sched.next_task()
    assert first is not None and first.name == "real"
    assert await sched.next_task() is None
    assert sched.close_all() == 1


def test_state_transitions_and_counts() -> None:
    sched = TaskScheduler()
    task = sched.submit(_value(1), name="a")
    assert task.state is TaskState.PENDING
    assert sched.counts()[TaskState.PENDING] == 1
    assert sched.submitted == 1
    assert sched.pending_count == 1

    sched.mark_running(task)
    assert task.started_at is not None
    assert sched.counts()[TaskState.RUNNING] == 1

    sched.mark_done(task, 42)
    assert task.result == 42
    assert task.duration is not None and task.duration >= 0
    assert sched.counts()[TaskState.DONE] == 1
    assert sched.pending_count == 0


def test_double_finish_raises() -> None:
    sched = TaskScheduler()
    task = sched.submit(_value(1), name="a")
    sched.mark_done(task, None)
    with pytest.raises(ValueError):
        sched.mark_failed(task, RuntimeError("late"))


def test_mark_failed_records_error() -> None:
    sched = TaskScheduler()
    task = sched.submit(_value(1), name="a")
    sched.mark_running(task)
    err = RuntimeError("boom")
    sched.mark_failed(task, err)
    assert task.error is err
    assert sched.counts()[TaskState.FAILED] == 1


def test_cancel_pending_closes_coroutines() -> None:
    sched = TaskScheduler()
    t1: Task = sched.submit(_value(1), name="a")
    t2: Task = sched.submit(_value(2), name="b")
    cancelled = sched.cancel_pending()
    assert cancelled == 2
    assert t1.state is TaskState.CANCELLED
    assert t2.state is TaskState.CANCELLED
    assert isinstance(t1.error, ScanCancelledError)
    assert t1.coro is None
    assert sched.counts()[TaskState.CANCELLED] == 2


def test_get_by_id_and_tasks_order() -> None:
    sched = TaskScheduler()
    a = sched.submit(_value(1), name="alpha")
    sched.submit(_value(2), name="beta")
    assert sched.get(a.id) is a
    assert sched.get("nope") is None
    assert [t.name for t in sched.tasks] == ["alpha", "beta"]
    assert sched.close_all() == 2


def test_unique_ids() -> None:
    sched = TaskScheduler()
    ids = {sched.submit(_value(1), name="t").id for _ in range(10)}
    assert len(ids) == 10
    assert sched.close_all() == 10
