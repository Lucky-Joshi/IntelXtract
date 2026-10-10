"""End-to-end Phase 14: metadata module -> engine -> persistence (offline)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType
from core.engine import ScanEngine
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink
from database.repositories import Repositories
from fakes import FakeHttpClient, make_module_config
from modules.registry import ModuleRegistry

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


async def _engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    persist: bool = False,
) -> ScanEngine:
    client = FakeHttpClient()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    kwargs: dict[str, Any] = {
        "modules": ModuleRegistry(packages=("modules.metadata",)).instances(),
        "timeout": 10.0,
        "concurrency": 4,
    }
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(make_module_config(tmp_path), **kwargs)


async def test_quick_file_scan_runs_metadata_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "sample.pdf"
    shutil.copyfile(FIXTURE_DIR / "sample.pdf", pdf)
    engine = await _engine(tmp_path, monkeypatch)

    result = await engine.scan(str(pdf), mode=ScanMode.QUICK)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.FILE
    runs = {run.module: run for run in result.runs}
    assert set(runs) == {"metadata"}
    assert runs["metadata"].status is ModuleStatus.SUCCESS

    titles = {finding["title"] for finding in result.findings}
    assert "Metadata: PDF properties" in titles
    pdf_finding = next(
        finding
        for finding in result.findings
        if finding["title"] == "Metadata: PDF properties"
    )
    assert pdf_finding["data"]["author"] == "Jane Analyst"
    assert pdf_finding["severity"] == "info"


async def test_quick_file_scan_persists_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jpg = tmp_path / "sample.jpg"
    shutil.copyfile(FIXTURE_DIR / "sample.jpg", jpg)
    engine = await _engine(tmp_path, monkeypatch, persist=True)

    result = await engine.scan(str(jpg), mode=ScanMode.QUICK)
    assert result.findings
    assert result.status is ScanStatus.COMPLETED

    db = Database(tmp_path / "intelxtract.db")
    await db.connect()
    try:
        repos = Repositories(db)
        scan = await repos.scans.get_by_uuid(result.scan_id)
        assert scan is not None
        records = await repos.findings.list_for_scan(scan.id)
        modules = {record.module for record in records}
        assert modules == {"metadata"}
        assert len(records) == len(result.findings)
    finally:
        await db.close()
