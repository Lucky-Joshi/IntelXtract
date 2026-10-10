"""End-to-end Phase 11: email modules -> engine -> persistence (all mocked)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType
from core.engine import ScanEngine
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink
from database.repositories import Repositories
from fakes import FakeHttpClient, make_module_config
from modules.registry import ModuleRegistry

DOH_URL = "https://cloudflare-dns.com/dns-query"
GRAVATAR_URL = "https://www.gravatar.com/avatar/"
TARGET = "alice@example.com"
BREACH_URL = (
    "https://haveibeenpwned.com/api/v3/breachedaccount/"
    f"{quote(TARGET, safe='')}?truncateResponse=false"
)


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
    client.stub(
        DOH_URL,
        body=_doh_handler(
            {
                ("example.com", "MX"): [{"data": "10 mail.example.com."}],
                ("mail.example.com", "A"): [{"data": "203.0.113.10"}],
                ("example.com", "TXT"): [
                    {"data": '"v=spf1 include:_spf.example.com -all"'}
                ],
                ("_dmarc.example.com", "TXT"): [{"data": '"v=DMARC1; p=quarantine"'}],
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
    registry = ModuleRegistry(packages=("modules.email",))
    kwargs.setdefault("modules", registry.instances())
    kwargs.setdefault("timeout", 5.0)
    kwargs.setdefault("concurrency", 2)
    if persist:
        db = Database(tmp_path / "intelxtract.db")
        await db.connect()
        await migrate(db)
        kwargs["result_sink"] = make_result_sink(db)
    return ScanEngine(cfg, **kwargs), client


async def test_quick_email_scan_runs_collector_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan(TARGET, mode=ScanMode.QUICK)

    assert result.status is ScanStatus.COMPLETED
    assert result.target_type is TargetType.EMAIL
    runs = {r.module: r for r in result.runs}
    assert set(runs) == {"email"}
    assert runs["email"].status is ModuleStatus.SUCCESS

    titles = {f["title"] for f in result.findings}
    assert "Email: MX records" in titles
    assert "Email: SPF policy" in titles
    assert "Email: DMARC policy" in titles


async def test_deep_email_scan_skips_breach_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    result = await engine.scan(TARGET, mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    runs = {r.module: r for r in result.runs}
    # breach is selected but its api key is unconfigured -> skipped, no error
    assert runs["breach"].status is ModuleStatus.SKIPPED
    assert "missing api key(s): hibp" in (runs["breach"].error or "")
    assert runs["email"].status is ModuleStatus.SUCCESS
    assert all(r.status is not ModuleStatus.FAILED for r in runs.values())


async def test_deep_email_scan_with_key_returns_breach_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _client = await _engine(tmp_path, monkeypatch)
    cfg = make_module_config(tmp_path, key="hibp", secret="unit-test-key")
    engine = ScanEngine(
        cfg,
        modules=ModuleRegistry(packages=("modules.email",)).instances(),
        timeout=5.0,
        concurrency=2,
    )
    _client.stub(BREACH_URL, status=404, body="")
    result = await engine.scan(TARGET, mode=ScanMode.DEEP)

    assert result.status is ScanStatus.COMPLETED
    runs = {r.module: r for r in result.runs}
    assert runs["breach"].status is ModuleStatus.SUCCESS
    assert any(f["title"] == "Breach: no known breaches" for f in result.findings)


async def test_quick_email_scan_persists_findings(
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
        assert "email" in modules
        assert len(records) == len(result.findings)
    finally:
        await db.close()
