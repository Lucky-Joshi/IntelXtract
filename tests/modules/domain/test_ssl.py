"""TLS (Phase 8, S8.3) SSL module tests with a monkeypatched handshake."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.constants import Severity
from fakes import make_module_config, make_module_context
from modules.domain import ssl as ssl_mod

now_future: dict[str, Any] = {
    "subject": ((("commonName", "example.com"),),),
    "issuer": ((("organizationName", "Let's Encrypt"),),),
    "notBefore": "Sep  1 00:00:00 2024 GMT",
    "notAfter": "Jan  1 00:00:00 2027 GMT",
    "serialNumber": "AB12",
    "subjectAltName": (("DNS", "example.com"), ("DNS", "www.example.com")),
}

now_past: dict[str, Any] = {**now_future, "notAfter": "Jan  1 00:00:00 2020 GMT"}

self_signed: dict[str, Any] = {
    **now_future,
    "issuer": ((("commonName", "example.com"),),),
}


def _norm(cert: dict[str, Any]) -> dict[str, Any]:
    return ssl_mod._normalize_cert(cert, "example.com")


def _patch(monkeypatch: pytest.MonkeyPatch, value: dict[str, Any] | None) -> None:
    async def fake(
        host: str, *, port: int = 443, timeout_seconds: float = 10.0
    ) -> dict[str, Any] | None:
        return value

    monkeypatch.setattr(ssl_mod, "_get_peer_cert", fake)


def test_normalize_cert_projects_fields() -> None:
    cert = _norm(now_future)

    assert cert["host"] == "example.com"
    assert cert["subject_cn"] == ["example.com"]
    assert cert["issuer"] == ["Let's Encrypt"]
    assert cert["issued"] == "2024-09-01T00:00:00+00:00"
    assert cert["expires"] == "2027-01-01T00:00:00+00:00"
    assert cert["expired"] is False
    assert cert["serial"] == "AB12"
    assert cert["subject_alt_names"] == ["example.com", "www.example.com"]
    assert cert["self_signed"] is False


def test_normalize_cert_flags_expired_certificate() -> None:
    assert _norm(now_past)["expired"] is True


def test_normalize_cert_flags_self_signed() -> None:
    assert _norm(self_signed)["self_signed"] is True


async def test_ssl_reports_certificate_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, _norm(now_future))
    cfg = make_module_config(tmp_path)
    ctx = make_module_context(cfg)

    result = await ssl_mod.SslModule().run("example.com", ctx)

    titles = {f.title for f in result.findings}
    assert "SSL: certificate" in titles
    assert "SSL: subject alternative names" in titles
    assert "SSL: self-signed certificate" not in titles
    assert "SSL: certificate expired" not in titles
    assert result.data["certificate"]["subject_alt_names"] == [
        "example.com",
        "www.example.com",
    ]


async def test_ssl_flags_self_signed_and_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = _norm(self_signed)
    bad["expires"] = "2020-01-01T00:00:00+00:00"
    bad["expired"] = True
    _patch(monkeypatch, bad)
    cfg = make_module_config(tmp_path)
    ctx = make_module_context(cfg)

    result = await ssl_mod.SslModule().run("example.com", ctx)

    by_title = {f.title: f for f in result.findings}
    assert by_title["SSL: self-signed certificate"].severity is Severity.MEDIUM
    assert by_title["SSL: certificate expired"].severity is Severity.HIGH


async def test_ssl_unreachable_reports_low_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, None)
    cfg = make_module_config(tmp_path)
    ctx = make_module_context(cfg)

    result = await ssl_mod.SslModule().run("example.com", ctx)

    assert result.data["state"] == "unreachable"
    finding = result.findings[0]
    assert finding.title == "SSL: no TLS certificate reachable on port 443"
    assert finding.severity is Severity.LOW
