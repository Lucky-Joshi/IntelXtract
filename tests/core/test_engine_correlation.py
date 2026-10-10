"""Phase 16 engine integration: a scan carries a deterministic correlation graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.constants import ScanMode, ScanStatus
from core.engine import ScanEngine
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


async def _engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScanEngine:
    client = _stubbed_client()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    await _patch_ssl(monkeypatch)
    cfg = make_module_config(tmp_path)
    cfg.set("whois.redact_emails", False)
    return ScanEngine(
        cfg,
        modules=ModuleRegistry(packages=("modules.domain",)).instances(),
        timeout=5.0,
        concurrency=2,
    )


async def test_deep_scan_builds_connected_correlation_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = await _engine(tmp_path, monkeypatch)
    result = await engine.scan("example.com", mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    correlation = result.correlation
    assert correlation is not None

    kinds = {item["kind"] for item in correlation["entities"]}
    assert {"domain", "ip", "organization", "email"} <= kinds

    values_by_kind: dict[str, set[str]] = {}
    for entity in correlation["entities"]:
        values_by_kind.setdefault(entity["kind"], set()).add(entity["value"])
    assert "example.com" in values_by_kind["domain"]
    assert "93.184.216.34" in values_by_kind["ip"]
    assert any("iana" in value for value in values_by_kind["email"])

    # domain -> IP must be linked
    edges = {
        (edge["source"], edge["target"]): edge["type"] for edge in correlation["edges"]
    }
    ip_ids = {
        entity["id"]
        for entity in correlation["entities"]
        if entity["kind"] == "ip" and entity["value"] == "93.184.216.34"
    }
    domain_ids = {
        entity["id"]
        for entity in correlation["entities"]
        if entity["kind"] == "domain" and entity["value"] == "example.com"
    }
    assert any(
        (domain_id, ip_id) in edges for domain_id in domain_ids for ip_id in ip_ids
    )

    assert correlation["stats"]["entities"] == len(correlation["entities"])
    assert correlation["stats"]["edges"] == len(correlation["edges"])


async def test_correlation_is_deterministic_across_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await _engine(tmp_path, monkeypatch)
    second = await _engine(tmp_path, monkeypatch)

    scan_a = await first.scan("example.com", mode=ScanMode.DEEP)
    scan_b = await second.scan("example.com", mode=ScanMode.DEEP)

    assert scan_a.correlation is not None
    assert scan_a.correlation == scan_b.correlation

    payload = scan_a.to_dict()
    assert payload["correlation"] == scan_a.correlation
