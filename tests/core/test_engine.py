"""Scan engine orchestration tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from core.cache import AsyncTTLCache
from core.config import Config
from core.constants import ModuleStatus, ScanStatus, TargetType
from core.engine import ModuleContext, ModuleRun, ScanEngine, ScanResult
from core.exceptions import ValidationError


class FakeModule:
    """Minimal module conforming to the Phase 2 protocol."""

    def __init__(
        self,
        name: str = "fake",
        *,
        target_types: tuple[TargetType, ...] = (),
        result: Any = None,
        error: Exception | None = None,
        delay: float = 0.0,
        valid: bool = True,
    ) -> None:
        self.name = name
        self.target_types = target_types
        self.result = {"payload": 1} if result is None else result
        self.error = error
        self.delay = delay
        self.valid = valid
        self.seen: list[str] = []

    def validate(self, target: str) -> bool:
        return self.valid

    async def run(self, target: str, ctx: ModuleContext) -> Any:
        self.seen.append(target)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.result


def _engine(tmp_path: Path, **kwargs: Any) -> ScanEngine:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    kwargs.setdefault("cache", AsyncTTLCache(max_size=8, default_ttl=60.0))
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("concurrency", 4)
    return ScanEngine(cfg, **kwargs)


async def test_scan_with_no_modules(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = await engine.scan("example.com")
    assert result.status is ScanStatus.COMPLETED
    assert result.runs == []
    assert result.findings == []
    assert result.error is None
    assert result.target == "example.com"
    assert result.target_type is TargetType.DOMAIN
    assert result.duration >= 0
    assert len(result.scan_id) == 12


async def test_successful_module_run(tmp_path: Path) -> None:
    module = FakeModule(result={"whois": "data"})
    engine = _engine(tmp_path, modules=[module])
    result = await engine.scan("example.com")
    assert module.seen == ["example.com"]
    run = next(r for r in result.runs if r.module == "fake")
    assert run.status is ModuleStatus.SUCCESS
    assert run.result == {"whois": "data"}
    assert run.duration > 0
    assert result.findings == [{"module": "fake", "data": {"whois": "data"}}]


async def test_module_failure_does_not_fail_scan(tmp_path: Path) -> None:
    module = FakeModule(error=ValueError("module blew up"))
    engine = _engine(tmp_path, modules=[module])
    result = await engine.scan("example.com")
    assert result.status is ScanStatus.COMPLETED
    run = result.runs[0]
    assert run.status is ModuleStatus.FAILED
    assert "module blew up" in (run.error or "")
    assert result.failed_count == 1
    assert result.findings == []


async def test_module_timeout(tmp_path: Path) -> None:
    module = FakeModule(delay=5.0)
    engine = _engine(tmp_path, modules=[module], timeout=0.05)
    result = await engine.scan("example.com")
    run = result.runs[0]
    assert run.status is ModuleStatus.TIMEOUT
    assert "timed out" in (run.error or "")


async def test_target_type_mismatch_is_skipped(tmp_path: Path) -> None:
    module = FakeModule(target_types=(TargetType.DOMAIN,))
    engine = _engine(
        tmp_path,
        modules=[module],
        classifier=lambda _t: TargetType.IP,
    )
    result = await engine.scan("1.2.3.4")
    run = result.runs[0]
    assert run.status is ModuleStatus.SKIPPED
    assert "not applicable" in (run.error or "")
    assert module.seen == []


async def test_validation_failure_inside_module_is_skipped(tmp_path: Path) -> None:
    module = FakeModule(valid=False)
    engine = _engine(tmp_path, modules=[module])
    result = await engine.scan("whatever")
    assert result.runs[0].status is ModuleStatus.SKIPPED
    assert module.seen == []


async def test_module_name_filter(tmp_path: Path) -> None:
    a = FakeModule(name="a")
    b = FakeModule(name="b")
    engine = _engine(tmp_path, modules=[a, b])
    result = await engine.scan("x", module_names=["b"])
    assert [r.module for r in result.runs] == ["b"]
    assert b.seen == ["x"]
    assert a.seen == []


async def test_unknown_module_name_raises(tmp_path: Path) -> None:
    engine = _engine(tmp_path, modules=[FakeModule()])
    with pytest.raises(ValidationError, match="unknown module"):
        await engine.scan("x", module_names=["ghost"])


async def test_invalid_targets_raise(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with pytest.raises(ValidationError):
        await engine.scan("")
    with pytest.raises(ValidationError):
        await engine.scan("   ")
    with pytest.raises(ValidationError):
        await engine.scan("x" * 3000)


async def test_classifier_injection(tmp_path: Path) -> None:
    engine = _engine(tmp_path, classifier=lambda _t: TargetType.EMAIL)
    result = await engine.scan("user@example.com")
    assert result.target_type is TargetType.EMAIL


async def test_result_sink_called(tmp_path: Path) -> None:
    captured: list[ScanResult] = []

    async def sink(result: ScanResult) -> None:
        captured.append(result)

    engine = _engine(tmp_path, modules=[FakeModule()], result_sink=sink)
    await engine.scan("example.com")
    assert len(captured) == 1
    assert captured[0].target == "example.com"


async def test_register_rejects_unnamed_module(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with pytest.raises(ValidationError):
        engine.register(FakeModule(name=""))


async def test_multiple_modules_all_run(tmp_path: Path) -> None:
    modules = [FakeModule(name=f"m{i}", result={"i": i}) for i in range(5)]
    engine = _engine(tmp_path, modules=modules, concurrency=3)
    result = await engine.scan("example.com")
    assert len(result.runs) == 5
    assert all(r.status is ModuleStatus.SUCCESS for r in result.runs)
    assert len(result.findings) == 5
    assert engine.module_names() == ["m0", "m1", "m2", "m3", "m4"]


async def test_result_to_dict_is_serializable(tmp_path: Path) -> None:
    import json

    engine = _engine(tmp_path, modules=[FakeModule()])
    result = await engine.scan("example.com")
    payload = result.to_dict()
    assert json.loads(json.dumps(payload))["target"] == "example.com"
    assert payload["runs"][0]["status"] == "success"


async def test_on_module_done_receives_live_outcomes(tmp_path: Path) -> None:
    events: list[ModuleRun] = []
    modules = [
        FakeModule(name="alpha", result={"ok": 1}),
        FakeModule(name="beta", error=RuntimeError("boom")),
    ]
    engine = _engine(tmp_path, modules=modules, on_module_done=events.append)
    result = await engine.scan("example.com")
    assert sorted(event.module for event in events) == ["alpha", "beta"]
    live = {event.module: event.status for event in events}
    assert live["alpha"] is ModuleStatus.SUCCESS
    assert live["beta"] is ModuleStatus.FAILED
    final = {run.module: run.status for run in result.runs}
    assert final == live


async def test_on_module_done_skipped_modules_not_reported(
    tmp_path: Path,
) -> None:
    events: list[ModuleRun] = []
    modules = [
        FakeModule(name="ok", target_types=(TargetType.DOMAIN,)),
        FakeModule(name="ip_only", target_types=(TargetType.IP,)),
    ]
    engine = _engine(
        tmp_path,
        modules=modules,
        on_module_done=events.append,
        classifier=lambda _t: TargetType.DOMAIN,
    )
    result = await engine.scan("example.com")
    assert [event.module for event in events] == ["ok"]
    skipped = next(r for r in result.runs if r.module == "ip_only")
    assert skipped.status is ModuleStatus.SKIPPED
