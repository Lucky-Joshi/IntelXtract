"""End-to-end offline scans against a local mock HTTP server (S26.3).

These tests exercise the full production path — ``ScanEngine`` -> shared
``HttpClient`` -> real aiohttp transport -> collectors — but every endpoint
is a loopback mock, so the suite never touches the public internet.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web

from core.config import Config
from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType
from core.engine import ScanEngine
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink
from database.repositories import Repositories
from fakes import make_module_config
from modules.domain.dns import DnsModule
from modules.domain.subdomain import SubdomainModule
from modules.domain.whois import WhoisModule
from modules.ip.geo import GeoModule
from modules.ip.rdns import RdnsModule
from modules.ip.reputation import ReputationModule


def _doh_answers(name: str, rtype: str) -> list[dict[str, object]]:
    name = name.rstrip(".")
    if rtype == "PTR":
        if name == "4.3.2.1.in-addr.arpa":
            return [{"name": name, "type": 12, "TTL": 300, "data": "host.example.com."}]
        return []
    if rtype == "TXT":
        if name.startswith("_dmarc."):
            return [
                {"name": name, "type": 16, "TTL": 300, "data": '"v=DMARC1; p=none"'}
            ]
        if "._domainkey." in name:
            return [
                {
                    "name": name,
                    "type": 16,
                    "TTL": 300,
                    "data": '"v=DKIM1; k=rsa; p=abc"',
                }
            ]
        if name == "example.com":
            return [{"name": name, "type": 16, "TTL": 300, "data": '"v=spf1 -all"'}]
        return []
    if name == "host.example.com" and rtype == "A":
        return [{"name": name, "type": 1, "TTL": 300, "data": "1.2.3.4"}]
    if name == "example.com":
        table = {
            "A": (1, "93.184.216.34"),
            "AAAA": (28, "2606:2800:220:1:248:1893:25c8:1946"),
            "NS": (2, "ns1.example.com."),
            "MX": (15, "10 mail.example.com."),
        }
        if rtype in table:
            rtype_num, data = table[rtype]
            return [{"name": name, "type": rtype_num, "TTL": 300, "data": data}]
    return []


async def _doh(request: web.Request) -> web.Response:
    answers = _doh_answers(
        request.query.get("name", ""), request.query.get("type", "A")
    )
    return web.json_response({"Status": 0 if answers else 3, "Answer": answers})


async def _rdap(request: web.Request) -> web.Response:
    domain = request.match_info.get("name", "")
    payload = {
        "objectClassName": "domain",
        "ldhName": domain.upper(),
        "status": ["active", "client transfer prohibited"],
        "events": [
            {"eventAction": "registration", "eventDate": "2000-01-01T00:00:00Z"},
            {"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"},
            {"eventAction": "last changed", "eventDate": "2024-01-01T00:00:00Z"},
        ],
        "nameservers": [
            {"ldhName": "NS1.EXAMPLE.COM"},
            {"ldhName": "NS2.EXAMPLE.COM"},
        ],
        "secureDNS": {"delegationSigned": True},
        "registrar": [{"ldhName": "Example Registrar, Inc."}],
        "entities": [
            {
                "roles": ["registrar"],
                "vcardArray": [
                    "vcard",
                    [
                        ["fn", {}, "text", "Example Registrar, Inc."],
                        ["email", {}, "text", "abuse@registrar.test"],
                    ],
                ],
            }
        ],
    }
    return web.json_response(payload)


async def _crt_sh(request: web.Request) -> web.Response:
    entries = [
        {
            "id": 2,
            "name_value": "www.example.com\napi.example.com",
            "common_name": "www.example.com",
            "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
            "not_before": "2024-01-01T00:00:00",
            "not_after": "2024-04-01T00:00:00",
            "entry_timestamp": "2024-01-01T00:00:00",
        },
        {
            "id": 1,
            "name_value": "example.com",
            "common_name": "example.com",
            "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
            "not_before": "2023-01-01T00:00:00",
            "not_after": "2023-04-01T00:00:00",
            "entry_timestamp": "2023-01-01T00:00:00",
        },
    ]
    return web.Response(text=json.dumps(entries), content_type="application/json")


async def _geo(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "success",
            "query": request.match_info.get("ip", ""),
            "country": "United States",
            "countryCode": "US",
            "region": "California",
            "city": "Los Angeles",
            "timezone": "America/Los_Angeles",
            "lat": 34.05,
            "lon": -118.24,
            "isp": "Example ISP",
            "org": "Example Org",
            "as": "AS64500 Example ISP",
        }
    )


@pytest.fixture
async def mock_endpoints() -> AsyncIterator[str]:
    """Start the mock endpoints on loopback and yield the base URL."""
    app = web.Application()
    app.router.add_get("/dns-query", _doh)
    app.router.add_get("/rdap/domain/{name}", _rdap)
    app.router.add_get("/crt.sh", _crt_sh)
    app.router.add_get("/geo/{ip}", _geo)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    host, port = runner.addresses[0]
    try:
        yield f"http://{host}:{port}"
    finally:
        await runner.cleanup()


def _cfg(tmp_path: Path, base_url: str) -> Config:
    cfg = make_module_config(tmp_path)
    cfg.set("dns.endpoint", f"{base_url}/dns-query")
    cfg.set("dns.selectors", ["default"])
    cfg.set("whois.endpoint", f"{base_url}/rdap/domain/")
    cfg.set("subdomain.endpoint", f"{base_url}/crt.sh")
    cfg.set("rdns.endpoint", f"{base_url}/dns-query")
    cfg.set("reputation.endpoint", f"{base_url}/dns-query")
    cfg.set("geo.endpoint", f"{base_url}/geo/")
    return cfg


def _titles(result: Any, module: str) -> set[str]:
    return {
        finding["title"] for finding in result.findings if finding["module"] == module
    }


async def test_domain_scan_end_to_end_offline(
    tmp_path: Path, mock_endpoints: str
) -> None:
    modules: list[Any] = [DnsModule(), WhoisModule(), SubdomainModule()]
    engine = ScanEngine(
        _cfg(tmp_path, mock_endpoints),
        modules=modules,
        timeout=10.0,
        concurrency=3,
    )
    result = await engine.scan("example.com", mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.DOMAIN
    runs = {run.module: run for run in result.runs}
    assert set(runs) == {"dns", "whois", "subdomain"}
    assert all(run.status is ModuleStatus.SUCCESS for run in runs.values()), {
        name: run.error for name, run in runs.items()
    }

    dns_titles = _titles(result, "dns")
    assert "DNS: A records" in dns_titles
    a_records = next(
        finding["data"]["records"]
        for finding in result.findings
        if finding["module"] == "dns" and finding["title"] == "DNS: A records"
    )
    assert "93.184.216.34" in a_records
    assert "DNS: SPF record" in dns_titles
    assert "DNS: DMARC record" in dns_titles

    whois_titles = _titles(result, "whois")
    assert "RDAP: registrar" in whois_titles
    assert "RDAP: DNSSEC signed" in whois_titles

    sub_titles = _titles(result, "subdomain")
    assert "Subdomains: certificate transparency" in sub_titles
    subdomains = next(
        finding["data"]["subdomains"]
        for finding in result.findings
        if finding["module"] == "subdomain"
    )
    assert {"api.example.com", "www.example.com"}.issubset(set(subdomains))


async def test_ip_scan_end_to_end_offline(tmp_path: Path, mock_endpoints: str) -> None:
    modules: list[Any] = [GeoModule(), RdnsModule(), ReputationModule()]
    engine = ScanEngine(
        _cfg(tmp_path, mock_endpoints),
        modules=modules,
        timeout=10.0,
        concurrency=3,
    )
    result = await engine.scan("1.2.3.4", mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.IP
    runs = {run.module: run for run in result.runs}
    assert set(runs) == {"geo", "rdns", "reputation"}
    assert all(run.status is ModuleStatus.SUCCESS for run in runs.values()), {
        name: run.error for name, run in runs.items()
    }

    geo_titles = _titles(result, "geo")
    assert "Geo: IP location" in geo_titles
    assert "Geo: network" in geo_titles

    assert "RDNS: forward-confirmed" in _titles(result, "rdns")
    assert "Reputation: DNSBL clean" in _titles(result, "reputation")


async def test_domain_scan_persists_through_sink_offline(
    tmp_path: Path, mock_endpoints: str
) -> None:
    db = Database(tmp_path / "intelxtract.db")
    await db.connect()
    try:
        await migrate(db)
        modules: list[Any] = [DnsModule(), SubdomainModule()]
        engine = ScanEngine(
            _cfg(tmp_path, mock_endpoints),
            modules=modules,
            timeout=10.0,
            concurrency=2,
            result_sink=make_result_sink(db),
        )
        result = await engine.scan("example.com", mode=ScanMode.DEEP)
        assert result.status is ScanStatus.COMPLETED

        repos = Repositories(db)
        scan = await repos.scans.get_by_uuid(result.scan_id)
        assert scan is not None
        records = await repos.findings.list_for_scan(scan.id)
        persisted_modules = {record.module for record in records}
        assert {"dns", "subdomain"}.issubset(persisted_modules)
        assert all(record.content_hash for record in records)
    finally:
        await db.close()
