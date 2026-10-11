"""Phase 25 (S25.6): benchmark script smoke tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_bench() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "bench.py"
    spec = importlib.util.spec_from_file_location("ix_bench", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_run_benchmarks_quick_reports_sections() -> None:
    bench = _load_bench()
    results = await bench.run_benchmarks(quick=True)

    assert set(results) == {"cache", "engine", "offload"}
    assert results["cache"]["ops_per_second"] > 0
    assert results["cache"]["hit_rate"] == pytest.approx(1.0)
    assert results["engine"]["scans_per_second"] > 0
    assert results["offload"]["ops_per_second"] > 0


def test_main_json_emits_parsable_output(capsys: pytest.CaptureFixture[str]) -> None:
    bench = _load_bench()
    assert bench.main(["--quick", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "engine" in payload
    assert "offload" in payload
