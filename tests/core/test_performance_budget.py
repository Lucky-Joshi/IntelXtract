"""Performance budget assertions on the cache and dedupe paths (S26.7).

Budgets are intentionally generous (orders of magnitude above the measured
baseline) so CI failures indicate a real regression, not machine noise.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.cache import AsyncTTLCache
from core.constants import Severity, TargetType
from core.engine import ModuleContext, ScanEngine
from core.models import ModuleResult, make_finding
from fakes import make_module_config

CACHE_BUDGET_S = 5.0
SCAN_BUDGET_S = 5.0


class DummyModule:
    """Minimal module yielding one finding per scan."""

    name = "dummy"
    target_types: tuple[TargetType, ...] = ()

    def validate(self, target: str) -> bool:
        return bool(target and target.strip())

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        return ModuleResult(
            findings=[
                make_finding(
                    self.name,
                    f"hit {target}",
                    {"target": target},
                    severity=Severity.LOW,
                    confidence=0.9,
                )
            ]
        )


class TwinModule(DummyModule):
    """Emits the same finding digest as DummyModule to stress dedupe."""

    name = "twin"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        return ModuleResult(
            findings=[
                make_finding(
                    DummyModule.name,
                    f"hit {target}",
                    {"target": target},
                    severity=Severity.LOW,
                    confidence=0.9,
                )
            ]
        )


async def test_cache_warm_throughput_budget() -> None:
    cache = AsyncTTLCache(max_size=1 << 20, default_ttl=60.0)
    start = time.perf_counter()
    for i in range(100_000):
        await cache.set(str(i), i)
    for i in range(100_000):
        assert await cache.get(str(i)) == i
    elapsed = time.perf_counter() - start
    assert (
        elapsed < CACHE_BUDGET_S
    ), f"cache path too slow: {elapsed:.2f}s for 200k warm ops"


async def test_scan_throughput_and_dedupe_budget(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    engine = ScanEngine(
        cfg, modules=[DummyModule(), TwinModule()], timeout=5.0, concurrency=2
    )
    total = 0
    start = time.perf_counter()
    for i in range(300):
        result = await engine.scan(f"example{i}.com")
        assert len(result.findings) == 1
        assert result.findings[0]["module"] == "dummy"
        total += len(result.runs)
    elapsed = time.perf_counter() - start
    assert total == 600
    assert (
        elapsed < SCAN_BUDGET_S
    ), f"scan pipeline too slow: {elapsed:.2f}s for 300 deduped scans"


async def test_engine_cached_ctx_memoizes_factory(tmp_path: Path) -> None:
    """A memoized factory in a scan runs once and stays cheap on reuse."""
    calls: list[int] = []

    async def _memo_factory() -> str:
        calls.append(len(calls))
        return "once"

    class CountingModule(DummyModule):
        name = "counting"

        async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
            value = await ctx.cached("memo", _memo_factory, ttl=60.0)
            return ModuleResult(data={"memo": value})

    cfg = make_module_config(tmp_path)
    engine = ScanEngine(cfg, modules=[CountingModule()], timeout=5.0, concurrency=1)
    start = time.perf_counter()
    first = await engine.scan("example.com")
    second = await engine.scan("example.com")
    elapsed = time.perf_counter() - start
    assert first.runs[0].result["data"]["memo"] == "once"
    assert second.runs[0].result["data"]["memo"] == "once"
    assert calls == [0]
    assert elapsed < CACHE_BUDGET_S


def _mark_and_return(storage: list[int]) -> Any:
    storage.append(len(storage))
    return "once"
