"""End-to-end Phase 15: news module -> engine -> persistence (mocked)."""

from __future__ import annotations

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
from modules.news.rss import GOOGLE_NEWS_RSS
from modules.registry import ModuleRegistry

TARGET = "example.com"
BESPOKE_FEED = "https://bespoke.example/feed.xml"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "news"


def _client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(
        GOOGLE_NEWS_RSS, body=(FIXTURE_DIR / "feed.xml").read_text(encoding="utf-8")
    )
    client.stub(
        BESPOKE_FEED, body=(FIXTURE_DIR / "atom.xml").read_text(encoding="utf-8")
    )
    return client


async def _engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    persist: bool = False,
    with_feed: bool = True,
) -> tuple[ScanEngine, FakeHttpClient]:
    client = _client()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    cfg = make_module_config(tmp_path)
    if with_feed:
        cfg.set("news.feeds", [BESPOKE_FEED])
    kwargs: dict[str, Any] = {
        "modules": ModuleRegistry(packages=("modules.news",)).instances(),
        "timeout": 10.0,
        "concurrency": 4,
    }
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(cfg, **kwargs), client


async def _timeline_finding(result: Any) -> dict[str, Any]:
    return next(
        finding for finding in result.findings if finding["title"] == "News: timeline"
    )


async def test_deep_scan_yields_news_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch, with_feed=True)
    result = await engine.scan(TARGET, mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.DOMAIN
    runs = {run.module: run for run in result.runs}
    assert set(runs) == {"news"}
    assert runs["news"].status is ModuleStatus.SUCCESS

    timeline = await _timeline_finding(result)
    assert timeline["severity"] == "info"
    assert timeline["data"]["count"] == 4  # duplicates collapsed (dedupe)
    titles = [article["title"] for article in timeline["data"]["articles"]]
    assert titles == [
        "Example upgrade underway",
        "Example outage reported",
        "Breach at example.com",
        "Undated notice",
    ]
    assert result.runs[0].module == "news"


async def test_deep_scan_degrades_when_all_feeds_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeHttpClient()  # nothing stubbed -> HttpError on every feed
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    engine = ScanEngine(
        make_module_config(tmp_path),
        modules=ModuleRegistry(packages=("modules.news",)).instances(),
        timeout=10.0,
        concurrency=4,
    )

    result = await engine.scan(TARGET, mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert any(
        finding["title"] == "News: no recent articles found"
        and finding["severity"] == "low"
        for finding in result.findings
    )


async def test_deep_scan_persists_news_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch, persist=True)
    result = await engine.scan(TARGET, mode=ScanMode.DEEP)
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
        assert modules == {"news"}
        assert len(records) == len(result.findings)
    finally:
        await db.close()
