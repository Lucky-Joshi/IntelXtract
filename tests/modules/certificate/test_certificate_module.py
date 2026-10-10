"""Certificate collector tests (Phase 13, S13.1-S13.3).

The two live hooks (peer chain handshake, TLS protocol probe) are
monkeypatched so these tests never open a connection; only crt.sh runs
through the stubbed shared HTTP client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import crt_payload, make_cert_pem
from modules.certificate import collector
from modules.certificate.collector import CertificateModule
from modules.certificate.details import parse_pem

CRT_URL = "https://crt.sh"
DOMAIN = "example.com"

_TLS_REPORT: dict[str, Any] = {
    "host": DOMAIN,
    "versions": [
        {
            "version": "TLSv1.2",
            "supported": True,
            "cipher": "ECDHE-RSA-AES128-GCM-SHA256",
            "reason": "",
        },
        {
            "version": "TLSv1.3",
            "supported": True,
            "cipher": "TLS_AES_256_GCM_SHA384",
            "reason": "",
        },
    ],
    "negotiated": {
        "version": "TLSv1.3",
        "cipher": "TLS_AES_256_GCM_SHA384",
    },
}


def _patch_live(
    monkeypatch: pytest.MonkeyPatch, *, records: list[dict[str, Any]]
) -> None:
    async def fake_chain(host: str, *, timeout_seconds: float) -> list[dict[str, Any]]:
        return records

    async def fake_probe(host: str, *, timeout_seconds: float) -> dict[str, Any]:
        return _TLS_REPORT

    monkeypatch.setattr(collector, "fetch_chain_records", fake_chain)
    monkeypatch.setattr(collector, "probe_protocol", fake_probe)


def _crt_client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(
        CRT_URL, body=crt_payload(), headers={"content-type": "application/json"}
    )
    return client


async def test_collector_combines_chain_tls_and_ct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pem = make_cert_pem(subject_cn=DOMAIN, sans=(DOMAIN, "www.example.com"))
    _patch_live(monkeypatch, records=parse_pem(pem))
    client = _crt_client()
    ctx = make_module_context(make_module_config(tmp_path), http=client)

    result = await CertificateModule().run(DOMAIN, ctx)

    titles = {finding.title for finding in result.findings}
    assert "Certificate: chain details" in titles
    assert "Certificate: subject alternative names" in titles
    assert "Certificate: transparency history" in titles
    assert "TLS: supported protocol versions" in titles
    assert "TLS: negotiated cipher" in titles

    assert result.data["state"] == "ok"
    assert result.data["transparency"]["count"] == 5
    assert result.data["tls"]["negotiated"]["version"] == "TLSv1.3"

    san = next(
        finding
        for finding in result.findings
        if finding.title == "Certificate: subject alternative names"
    )
    assert san.data["subject_alt_names"] == [
        f"DNS:{DOMAIN}",
        "DNS:www.example.com",
    ]
    assert san.severity.value == "info"


async def test_collector_reports_weak_protocol_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pem = make_cert_pem(subject_cn=DOMAIN)
    _patch_live(monkeypatch, records=parse_pem(pem))
    monkeypatch.setattr(
        collector,
        "probe_protocol",
        lambda host, timeout_seconds: _legacy_report(),
    )
    ctx = make_module_context(make_module_config(tmp_path), http=_crt_client())

    result = await CertificateModule().run(DOMAIN, ctx)

    titles = {finding.title for finding in result.findings}
    assert "TLS: weak protocol version" in titles
    weak = [
        finding
        for finding in result.findings
        if finding.title == "TLS: weak protocol version"
    ]
    assert all(finding.severity.value == "medium" for finding in weak)


async def _legacy_report() -> dict[str, Any]:
    return {
        "host": DOMAIN,
        "versions": [
            {
                "version": "TLSv1",
                "supported": True,
                "cipher": "ECDHE-RSA-RC4-SHA",
                "reason": "",
            },
            {
                "version": "TLSv1.2",
                "supported": False,
                "cipher": None,
                "reason": "refused",
            },
        ],
        "negotiated": {"version": "TLSv1", "cipher": "ECDHE-RSA-RC4-SHA"},
    }


async def test_collector_degrades_without_chain_or_ct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_live(monkeypatch, records=[])
    monkeypatch.setattr(
        collector, "probe_protocol", lambda host, timeout_seconds: _empty_report()
    )
    client = FakeHttpClient()  # crt.sh unstubbed -> 404 -> empty history
    ctx = make_module_context(make_module_config(tmp_path), http=client)

    result = await CertificateModule().run(DOMAIN, ctx)

    assert result.data["state"] == "unknown"
    titles = {finding.title for finding in result.findings}
    assert "Certificate: transparency history unavailable" in titles
    assert not any(
        finding.title == "Certificate: chain details" for finding in result.findings
    )


async def _empty_report() -> dict[str, Any]:
    return {"host": DOMAIN, "versions": [], "negotiated": None}


async def test_collector_marks_partial_when_only_ct_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_live(monkeypatch, records=[])
    monkeypatch.setattr(
        collector, "probe_protocol", lambda host, timeout_seconds: _empty_report()
    )
    ctx = make_module_context(make_module_config(tmp_path), http=_crt_client())

    result = await CertificateModule().run(DOMAIN, ctx)

    assert result.data["state"] == "partial"
    assert "Certificate: transparency history" in {
        finding.title for finding in result.findings
    }
