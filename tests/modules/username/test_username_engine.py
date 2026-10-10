"""End-to-end Phase 12: username module -> engine -> persistence (mocked)."""

from __future__ import annotations

import json
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

TARGET = "octocat"
GITHUB_URL = f"https://github.com/{TARGET}"
GITHUB_API = f"https://api.github.com/users/{TARGET}"


def _stubbed_client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(GITHUB_URL, status=200, body="<html>octocat</html>")
    client.stub(
        GITHUB_API,
        status=200,
        body=(
            '{"login": "octocat", "name": "Mona Lisa", '
            '"avatar_url": "https://avatars/1.png", '
            '"html_url": "https://github.com/octocat", "bio": "Hello"}'
        ),
    )
    return client


async def _engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    persist: bool = False,
) -> tuple[ScanEngine, FakeHttpClient]:
    client = _stubbed_client()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    cfg = make_module_config(tmp_path)
    registry = ModuleRegistry(packages=("modules.username",))
    kwargs: dict[str, Any] = {
        "modules": registry.instances(),
        "timeout": 10.0,
        "concurrency": 4,
    }
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(cfg, **kwargs), client


async def test_quick_username_scan_runs_collector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan(TARGET, mode=ScanMode.QUICK)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.USERNAME
    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"username"}
    assert runs["username"].status is ModuleStatus.SUCCESS

    titles = {f["title"] for f in result.findings}
    assert "Username: profile summary" in titles
    assert "Username: exists on GitHub" in titles
    assert "Username: GitHub profile enrichment" in titles


async def test_username_scan_reports_unknown_when_all_sites_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeHttpClient()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    cfg = make_module_config(tmp_path)
    # single-site registry via override so every verdict is unconfirmed
    override = tmp_path / "sites.json"
    override.write_text(
        json.dumps(
            {
                "sites": [
                    {
                        "name": "BlockedOnly",
                        "url": "https://blocked.tld/{username}",
                        "rule": {"exists": [200], "missing": [], "unknown": [403, 410]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg.set("username.sites_path", str(override))
    engine = ScanEngine(
        cfg,
        modules=ModuleRegistry(packages=("modules.username",)).instances(),
        timeout=5.0,
        concurrency=2,
    )
    client.stub("https://blocked.tld/octocat", status=403, body="blocked")
    result = await engine.scan(TARGET, mode=ScanMode.QUICK)

    assert result.status is ScanStatus.COMPLETED
    runs = {r.module: r for r in result.runs}
    assert runs["username"].status is ModuleStatus.SUCCESS
    assert any(
        f["title"] == "Username: all site verdicts unknown" and f["severity"] == "low"
        for f in result.findings
    )
    site_entry = next(
        f for f in result.findings if f["title"] == "Username: profile summary"
    )
    assert site_entry["data"]["unknown"] == 1


async def test_quick_username_scan_persists_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch, persist=True)
    result = await engine.scan(TARGET, mode=ScanMode.QUICK)
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
        assert "username" in modules
        assert len(records) == len(result.findings)
    finally:
        await db.close()
