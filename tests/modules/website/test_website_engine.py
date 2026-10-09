"""End-to-end Phase 10: website modules -> engine -> persistence (all mocked)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.constants import ModuleStatus, ScanMode, ScanStatus, Severity, TargetType
from core.engine import ScanEngine
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink
from database.repositories import Repositories
from fakes import FakeHttpClient, make_module_config
from fixtures import favicon_bytes, robots_txt, sitemap_xml, tech_html
from modules.registry import ModuleRegistry

PAGE_URL = "https://example.com/"
ROBOTS_URL = "https://example.com/robots.txt"
SITEMAP_URL = "https://example.com/sitemap.xml"
FAV_URL = "https://example.com/favicon.ico"

PAGE_HEADERS = {
    "Server": "nginx",
    "X-Powered-By": "PHP/7.4",
    "Content-Encoding": "gzip",
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'",
    "X-Frame-Options": "DENY",
    "Set-Cookie": "session=abc123; Path=/; HttpOnly; Secure; SameSite=Lax",
}


def _method_handler() -> Any:
    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], str]:
        if method == "OPTIONS":
            return 200, {"Allow": "GET, HEAD, OPTIONS"}, ""
        if method == "HEAD":
            return 200, {"Content-Type": "text/html; charset=utf-8"}, ""
        return 200, PAGE_HEADERS, tech_html()

    return _handle


def _stubbed_client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(PAGE_URL, body=_method_handler())
    client.stub(ROBOTS_URL, body=robots_txt())
    client.stub(SITEMAP_URL, body=sitemap_xml())
    client.stub(FAV_URL, body=favicon_bytes(), headers={"Content-Type": "image/x-icon"})
    return client


async def _engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    persist: bool = False,
    **kwargs: Any,
) -> tuple[ScanEngine, FakeHttpClient]:
    client = _stubbed_client()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    cfg = make_module_config(tmp_path)
    registry = ModuleRegistry(packages=("modules.website",))
    kwargs.setdefault("modules", registry.instances())
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("concurrency", 2)
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(cfg, **kwargs), client


async def test_deep_website_scan_runs_all_collectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan(PAGE_URL, mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.URL
    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"headers", "tech", "favicon", "robots", "http_methods"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())

    titles = {f["title"] for f in result.findings}
    assert "Headers: server disclosure" in titles
    assert "Tech: WordPress" in titles
    assert "Favicon: fingerprint" in titles
    assert "Robots: sitemap URLs" in titles
    assert "HTTP: allowed methods" in titles
    assert any(f["severity"] == Severity.MEDIUM.value for f in result.findings)


async def test_quick_website_scan_runs_headers_and_methods_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan(PAGE_URL, mode=ScanMode.QUICK)

    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"headers", "http_methods"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())


async def test_quick_website_scan_persists_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch, persist=True)
    result = await engine.scan(PAGE_URL, mode=ScanMode.QUICK)
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
        assert {"headers", "http_methods"} <= modules
        assert len(records) == len(result.findings)
    finally:
        await db.close()
