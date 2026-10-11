"""Phase 25 (S25.4) offload pool tests."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from core.offload import (
    DEFAULT_WORKERS,
    OffloadPool,
    configure_offload,
    get_offload_pool,
    offload,
    shutdown_offload,
)


def test_pool_rejects_zero_workers() -> None:
    with pytest.raises(ValueError):
        OffloadPool(0)


def test_pool_default_workers() -> None:
    pool = OffloadPool()
    try:
        assert pool.max_workers == DEFAULT_WORKERS
        assert pool.stats.submitted == 0
    finally:
        pool.shutdown()


async def test_run_returns_value_from_worker_thread() -> None:
    loop_thread = threading.get_ident()
    pool = OffloadPool(2)
    seen: dict[str, int] = {}

    def blocking(value: int) -> int:
        seen["thread"] = threading.get_ident()
        return value * 2

    try:
        assert await pool.run(blocking, 21) == 42
    finally:
        await pool.aclose()

    assert seen["thread"] != loop_thread
    assert pool.stats.submitted == 1
    assert pool.stats.completed == 1


async def test_run_forwards_kwargs() -> None:
    pool = OffloadPool(1)
    try:
        assert await pool.run(round, 3.14159, ndigits=2) == 3.14
    finally:
        await pool.aclose()


async def test_pool_bounds_concurrency() -> None:
    pool = OffloadPool(2)
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def work() -> None:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1

    try:
        await asyncio.gather(*(pool.run(work) for _ in range(5)))
    finally:
        await pool.aclose()

    assert state["peak"] == 2
    assert state["active"] == 0


async def test_offload_keeps_loop_responsive() -> None:
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.001)

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0)
    try:
        await offload(time.sleep, 0.05)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert ticks >= 3


async def test_shared_pool_is_reused() -> None:
    await shutdown_offload()
    try:
        assert get_offload_pool() is get_offload_pool()
        assert await offload(int, "7") == 7
    finally:
        await shutdown_offload()


async def test_configure_replaces_shared_pool() -> None:
    await shutdown_offload()
    try:
        first = get_offload_pool()
        configure_offload(1)
        second = get_offload_pool()
        assert second is not first
        assert second.max_workers == 1
    finally:
        await shutdown_offload()
