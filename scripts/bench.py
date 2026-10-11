#!/usr/bin/env python3
"""Phase 25 (S25.6) performance benchmarks.

Measures cache throughput, engine scan throughput, and offload throughput so
the numbers in ``docs/performance.md`` can be reproduced on demand::

    python scripts/bench.py            # quick human-readable suite
    python scripts/bench.py --json     # machine-readable results
    python scripts/bench.py --quick    # reduced iteration counts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.cache import AsyncTTLCache
from core.config import Config
from core.constants import TargetType
from core.engine import ModuleContext, ScanEngine
from core.models import ModuleResult
from core.offload import OffloadPool, shutdown_offload


class _NoopModule:
    """Trivial collector so scan throughput measures engine overhead only."""

    name = "bench_noop"
    target_types: tuple[TargetType, ...] = (TargetType.DOMAIN,)

    def validate(self, target: str) -> bool:
        return True

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        return ModuleResult(data={"ok": True})


def _rate(count: int, elapsed: float) -> float:
    return count / elapsed if elapsed > 0 else float("inf")


def _config() -> Config:
    path = Path(tempfile.gettempdir()) / "intelxtract-bench-settings.json"
    return Config(path, use_env=False)


async def bench_cache(iterations: int) -> dict[str, float]:
    """Time ``set`` + hit-``get`` round trips through the TTL cache."""
    cache = AsyncTTLCache(max_size=max(iterations, 1024), default_ttl=300.0)
    start = time.perf_counter()
    for index in range(iterations):
        await cache.set(f"bench:{index}", index)
    for index in range(iterations):
        await cache.get(f"bench:{index}")
    elapsed = time.perf_counter() - start
    hits = cache.stats.hits
    return {
        "iterations": float(iterations),
        "elapsed_seconds": elapsed,
        "ops_per_second": _rate(iterations * 2, elapsed),
        "hit_rate": hits / iterations if iterations else 0.0,
    }


async def bench_engine(scans: int, modules: int) -> dict[str, float]:
    """Time full scans across ``modules`` trivial collectors."""
    engine = ScanEngine(
        _config(),
        modules=[_NoopModule() for _ in range(modules)],
        concurrency=8,
    )
    start = time.perf_counter()
    for index in range(scans):
        await engine.scan(f"bench{index}.example.com")
    elapsed = time.perf_counter() - start
    return {
        "scans": float(scans),
        "modules_per_scan": float(modules),
        "elapsed_seconds": elapsed,
        "scans_per_second": _rate(scans, elapsed),
    }


async def bench_offload(iterations: int, workers: int = 4) -> dict[str, float]:
    """Time dispatching trivial work onto a bounded thread pool."""
    pool = OffloadPool(workers)
    start = time.perf_counter()
    try:
        for _ in range(iterations):
            await pool.run(lambda: 1 + 1)
    finally:
        await pool.aclose()
    elapsed = time.perf_counter() - start
    return {
        "iterations": float(iterations),
        "workers": float(workers),
        "elapsed_seconds": elapsed,
        "ops_per_second": _rate(iterations, elapsed),
    }


async def run_benchmarks(*, quick: bool = False) -> dict[str, Any]:
    """Run the full suite and return a JSON-serializable result mapping."""
    scale = 0.25 if quick else 1.0
    results: dict[str, Any] = {
        "cache": await bench_cache(max(int(20_000 * scale), 100)),
        "engine": await bench_engine(max(int(200 * scale), 5), modules=8),
        "offload": await bench_offload(max(int(5_000 * scale), 100)),
    }
    await shutdown_offload()
    return results


def render(results: dict[str, Any]) -> str:
    """Format benchmark results for a terminal."""
    cache = results["cache"]
    engine = results["engine"]
    offload = results["offload"]
    return "\n".join(
        [
            "IntelXtract performance benchmarks",
            f"cache:   {cache['ops_per_second']:.0f} ops/s "
            f"(hit_rate={cache['hit_rate']:.2f})",
            f"engine:  {engine['scans_per_second']:.1f} scans/s "
            f"({engine['modules_per_scan']:.0f} modules/scan)",
            f"offload: {offload['ops_per_second']:.0f} ops/s "
            f"({offload['workers']:.0f} workers)",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="IntelXtract benchmarks")
    parser.add_argument("--quick", action="store_true", help="run a reduced suite")
    parser.add_argument("--json", action="store_true", help="emit JSON results")
    args = parser.parse_args(argv)
    results = asyncio.run(run_benchmarks(quick=args.quick))
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        print(render(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
