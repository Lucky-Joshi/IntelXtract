"""End-to-end Phase 9: IP modules -> engine -> persistence (all mocked)."""

from __future__ import annotations

import ipaddress
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
from fixtures import geo_payload
from modules.registry import ModuleRegistry

GEO_URL_V4 = "http://ip-api.com/json/1.1.1.1"
GEO_URL_V6 = "http://ip-api.com/json/2001:db8::1"
DOH_URL = "https://cloudflare-dns.com/dns-query"
V4_REVERSE = "1.1.1.1.in-addr.arpa"
_V6_EXPANDED = ipaddress.ip_address("2001:db8::1").exploded.replace(":", "")
V6_REVERSE = ".".join(reversed(_V6_EXPANDED)) + ".ip6.arpa"
ZEN_QUERY = "1.1.1.1.zen.spamhaus.org"


def _doh_handler(
    table: dict[tuple[str, str], list[dict[str, Any]]],
) -> Any:
    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        params = kwargs.get("params") or {}
        name = str(params.get("name", ""))
        dns_type = str(params.get("type", ""))
        answers = table.get((name, dns_type))
        if answers is None:
            return 200, {"content-type": "application/dns-json"}, {"Status": 0}
        return (
            200,
            {"content-type": "application/dns-json"},
            {"Status": 0, "Answer": answers},
        )

    return _handle


def _stubbed_client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(GEO_URL_V4, body=geo_payload())
    client.stub(GEO_URL_V6, body=geo_payload())
    client.stub(
        DOH_URL,
        body=_doh_handler(
            {
                (V4_REVERSE, "PTR"): [
                    {
                        "name": V4_REVERSE,
                        "type": 12,
                        "TTL": 60,
                        "data": "one.one.one.one",
                    }
                ],
                ("one.one.one.one", "A"): [
                    {"name": "one.one.one.one", "type": 1, "TTL": 60, "data": "1.1.1.1"}
                ],
                (ZEN_QUERY, "A"): [],
                (V6_REVERSE, "PTR"): [
                    {
                        "name": V6_REVERSE,
                        "type": 12,
                        "TTL": 60,
                        "data": "host.example.com.",
                    }
                ],
                ("host.example.com", "AAAA"): [
                    {
                        "name": "host.example.com",
                        "type": 28,
                        "TTL": 60,
                        "data": "2001:db8::1",
                    }
                ],
            }
        ),
    )
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
    registry = ModuleRegistry(packages=("modules.ip",))
    kwargs.setdefault("modules", registry.instances())
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("concurrency", 2)
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(cfg, **kwargs), client


async def test_deep_ipv4_scan_runs_all_ip_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan("1.1.1.1", mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.IP
    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"geo", "rdns", "reputation"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())

    titles = {f["title"] for f in result.findings}
    assert "Geo: IP location" in titles
    assert "Geo: network" in titles
    assert "RDNS: PTR record" in titles
    assert "RDNS: forward-confirmed" in titles
    assert "Reputation: DNSBL clean" in titles


async def test_deep_ipv6_scan_end_to_end_without_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan("2001:db8::1", mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"geo", "rdns", "reputation"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())

    titles = {f["title"] for f in result.findings}
    assert "RDNS: forward-confirmed" in titles
    assert "Reputation: IPv6 out of scope for DNSBL" in titles


async def test_quick_ip_scan_runs_geo_and_rdns_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan("1.1.1.1", mode=ScanMode.QUICK)

    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"geo", "rdns"}
    assert all(r.status is ModuleStatus.SUCCESS for r in runs.values())


async def test_quick_ip_scan_persists_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch, persist=True)
    result = await engine.scan("1.1.1.1", mode=ScanMode.QUICK)
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
        assert {"geo", "rdns"} <= modules
        assert len(records) == len(result.findings)
    finally:
        await db.close()
