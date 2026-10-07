"""End-to-end Phase 8: domain modules -> engine -> persistence (all mocked)."""

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
from fixtures import crt_payload, doh_handler, http_handler, rdap_payload
from modules.domain import ssl as ssl_mod
from modules.registry import ModuleRegistry

RDAP_URL = "https://rdap.org/domain/example.com"
DOH_URL = "https://cloudflare-dns.com/dns-query"
CRT_URL = "https://crt.sh"
PROBE_URLS = (
    "https://example.com/",
    "http://example.com/",
    "https://example.com/robots.txt",
    "https://example.com/sitemap.xml",
)


def _stubbed_client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(RDAP_URL, body=rdap_payload())
    client.stub(DOH_URL, body=doh_handler())
    client.stub(CRT_URL, body=crt_payload())
    for url in PROBE_URLS:
        client.stub(url, body=http_handler())
    return client


async def _patch_ssl(monkeypatch: pytest.MonkeyPatch) -> None:
    cert = {
        "host": "example.com",
        "subject_cn": ["example.com"],
        "issuer": ["Let's Encrypt"],
        "issued": "2024-09-01T00:00:00+00:00",
        "expires": "2027-01-01T00:00:00+00:00",
        "expired": False,
        "serial": "AB12",
        "subject_alt_names": ["example.com", "www.example.com"],
        "self_signed": False,
    }

    async def fake_get_peer_cert(
        host: str, *, port: int = 443, timeout_seconds: float = 10.0
    ) -> dict[str, object] | None:
        return cert

    monkeypatch.setattr(ssl_mod, "_get_peer_cert", fake_get_peer_cert)


async def _engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    persist: bool = False,
    **kwargs: Any,
) -> tuple[ScanEngine, FakeHttpClient]:
    client = _stubbed_client()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    await _patch_ssl(monkeypatch)
    cfg = make_module_config(tmp_path)
    registry = ModuleRegistry(packages=("modules.domain",))
    kwargs.setdefault("modules", registry.instances())
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("concurrency", 2)
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(cfg, **kwargs), client


async def test_deep_domain_scan_runs_all_domain_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan("example.com", mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.DOMAIN
    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"whois", "dns", "ssl", "subdomain", "http"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())

    titles = {f["title"] for f in result.findings}
    assert "RDAP: registrar" in titles
    assert "DNS: SPF record" in titles
    assert "SSL: certificate" in titles
    assert "Subdomains: certificate transparency" in titles
    assert "HTTP: https responds" in titles
    assert any(f["severity"] == Severity.INFO.value for f in result.findings)


async def test_deep_domain_scan_persists_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch, persist=True)
    result = await engine.scan("example.com", mode=ScanMode.DEEP)
    assert result.findings

    db = Database(tmp_path / "intelxtract.db")
    await db.connect()
    try:
        repos = Repositories(db)
        scan = await repos.scans.get_by_uuid(result.scan_id)
        assert scan is not None
        records = await repos.findings.list_for_scan(scan.id)
        modules = {record.module for record in records}
        assert {"whois", "dns", "ssl", "subdomain", "http"} <= modules
        assert len(records) == len(result.findings)
    finally:
        await db.close()


async def test_quick_domain_scan_runs_dns_and_http_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan("example.com", mode=ScanMode.QUICK)

    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"dns", "http"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())
