"""End-to-end Phase 13: certificate module -> engine -> persistence (mocked).

Live hooks (peer-chain handshake and TLS probe) are monkeypatched and
crt.sh is stubbed, so the scan runs fully offline.
"""

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
from fixtures import crt_payload, make_cert_pem
from modules.certificate import collector
from modules.certificate.details import parse_pem
from modules.registry import ModuleRegistry

TARGET = "example.com"
CRT_URL = "https://crt.sh"

_TLS_REPORT: dict[str, Any] = {
    "host": TARGET,
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
    "negotiated": {"version": "TLSv1.3", "cipher": "TLS_AES_256_GCM_SHA384"},
}


def _patch_live_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = make_cert_pem(
        subject_cn=TARGET, sans=(TARGET, "www.example.com"), is_ca=False
    )
    records = parse_pem(pem)

    async def fake_chain(host: str, *, timeout_seconds: float) -> list[dict[str, Any]]:
        return records

    async def fake_probe(host: str, *, timeout_seconds: float) -> dict[str, Any]:
        return _TLS_REPORT

    monkeypatch.setattr(collector, "fetch_chain_records", fake_chain)
    monkeypatch.setattr(collector, "probe_protocol", fake_probe)


def _client() -> FakeHttpClient:
    client = FakeHttpClient()
    client.stub(
        CRT_URL, body=crt_payload(), headers={"content-type": "application/json"}
    )
    return client


async def _engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    persist: bool = False,
) -> tuple[ScanEngine, FakeHttpClient]:
    _patch_live_hooks(monkeypatch)
    client = _client()
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)
    kwargs: dict[str, Any] = {
        "modules": ModuleRegistry(packages=("modules.certificate",)).instances(),
        "timeout": 10.0,
        "concurrency": 4,
    }
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(make_module_config(tmp_path), **kwargs), client


async def test_deep_scan_runs_certificate_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan(TARGET, mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.DOMAIN
    runs = {run.module: run for run in result.runs}
    assert set(runs) == {"certificate"}
    assert runs["certificate"].status is ModuleStatus.SUCCESS

    titles = {finding["title"] for finding in result.findings}
    assert "Certificate: chain details" in titles
    assert "Certificate: subject alternative names" in titles
    assert "Certificate: transparency history" in titles
    assert "TLS: supported protocol versions" in titles
    assert "TLS: negotiated cipher" in titles

    cert_run = next(
        finding
        for finding in result.findings
        if finding["title"] == "Certificate: chain details"
    )
    assert cert_run["data"]["subject"]["commonName"] == [TARGET]
    assert cert_run["severity"] == "info"


async def test_deep_scan_persists_certificate_findings(
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
        assert modules == {"certificate"}
        assert len(records) == len(result.findings)
    finally:
        await db.close()
