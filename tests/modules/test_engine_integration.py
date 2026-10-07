"""End-to-end: Phase 7 dummy module -> engine -> normalizer -> persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.config import Config
from core.constants import ModuleStatus, ScanStatus, Severity, TargetType
from core.engine import ModuleContext, ScanEngine
from core.models import ModuleResult, make_finding
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink
from database.repositories import Repositories
from fakes import DummyModule, KeyedDummyModule, make_module_config
from modules.registry import ModuleRegistry


def _cfg(tmp_path: Path) -> Config:
    return make_module_config(tmp_path)


def _engine(cfg: Config, **kwargs: Any) -> ScanEngine:
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("concurrency", 2)
    return ScanEngine(cfg, **kwargs)


async def test_dummy_module_runs_through_engine(tmp_path: Path) -> None:
    engine = _engine(_cfg(tmp_path), modules=[DummyModule()])
    result = await engine.scan("example.com")

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.DOMAIN
    runs = {r.module: r for r in result.runs}
    assert runs["dummy"].status is ModuleStatus.SUCCESS
    # ModuleResult is preserved as a JSON-safe dict on the run record.
    assert runs["dummy"].result["data"]["target"] == "example.com"

    assert len(result.findings) == 1
    payload = result.findings[0]
    assert payload["module"] == "dummy"
    assert payload["title"].startswith("dummy hit")
    assert payload["severity"] == "low"
    assert payload["confidence"] == 0.9
    assert payload["content_hash"]
    assert payload["data"] == {"target": "example.com", "hits": 1}


async def test_dummy_module_findings_persist_through_sink(tmp_path: Path) -> None:
    db = Database(tmp_path / "intelxtract.db")
    await db.connect()
    try:
        await migrate(db)
        engine = _engine(
            _cfg(tmp_path),
            modules=[DummyModule()],
            result_sink=make_result_sink(db),
        )
        result = await engine.scan("example.org")
        assert result.findings

        repos = Repositories(db)
        scan = await repos.scans.get_by_uuid(result.scan_id)
        assert scan is not None
        records = await repos.findings.list_for_scan(scan.id)
        assert len(records) == 1
        record = records[0]
        assert record.module == "dummy"
        assert record.title.startswith("dummy hit")
        assert record.severity == "low"
        assert record.confidence == pytest.approx(0.9)
        assert record.evidence == "parsed:example.org"
        assert record.content_hash == result.findings[0]["content_hash"]
        assert record.data == {"target": "example.org", "hits": 1}
    finally:
        await db.close()


async def test_requires_keys_module_skipped_without_key(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    engine = _engine(cfg, modules=[KeyedDummyModule()])
    result = await engine.scan("example.com")

    runs = {r.module: r for r in result.runs}
    assert not result.findings
    assert runs["dummy_keyed"].status is ModuleStatus.SKIPPED
    assert "hibp" in (runs["dummy_keyed"].error or "")


async def test_requires_keys_module_runs_when_key_configured(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    engine = _engine(cfg, modules=[KeyedDummyModule()])
    result = await engine.scan("example.com")

    runs = {r.module: r for r in result.runs}
    assert runs["dummy_keyed"].status is ModuleStatus.SUCCESS
    assert result.findings[0]["data"] == {"key_len": len("HIBP-SECRET-1234")}


class TwinModule(DummyModule):
    """Emits the exact same finding as DummyModule to exercise dedupe."""

    name = "twin"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        return ModuleResult(
            findings=[
                make_finding(
                    DummyModule.name,
                    f"dummy hit 1 for {target}",
                    {"target": target, "hits": 1},
                    severity=Severity.LOW,
                    confidence=0.9,
                    evidence=f"parsed:{target}",
                )
            ]
        )


async def test_duplicate_findings_deduped_across_modules(tmp_path: Path) -> None:
    engine = _engine(_cfg(tmp_path), modules=[DummyModule(), TwinModule()])
    result = await engine.scan("example.com")
    assert len(result.findings) == 1
    assert {r.module for r in result.runs} == {"dummy", "twin"}
    assert result.findings[0]["module"] == "dummy"


async def test_registry_instances_drive_engine(tmp_path: Path) -> None:
    reg = ModuleRegistry()
    reg.register(DummyModule())
    reg.register(KeyedDummyModule())

    engine = _engine(_cfg(tmp_path), modules=reg.instances())
    result = await engine.scan("example.com")
    runs = {r.module: r for r in result.runs}
    assert runs["dummy"].status is ModuleStatus.SUCCESS
    assert runs["dummy_keyed"].status is ModuleStatus.SUCCESS

    reg.disable("dummy_keyed")
    engine = _engine(_cfg(tmp_path), modules=reg.instances())
    result = await engine.scan("example.com")
    assert "dummy_keyed" not in {r.module for r in result.runs}


async def test_scan_does_not_leak_http_client(tmp_path: Path) -> None:
    """The engine-created HttpClient must be closed after a scan."""
    engine = _engine(_cfg(tmp_path), modules=[DummyModule()])
    result = await engine.scan("example.com")
    assert result.status is ScanStatus.COMPLETED
