"""crt.sh transparency aggregation tests (Phase 13, S13.3)."""

from __future__ import annotations

from pathlib import Path

from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import crt_payload
from modules.certificate.collector import CertificateModule
from modules.certificate.transparency import (
    aggregate_transparency,
    fetch_transparency,
)

CRT_URL = "https://crt.sh"
DOMAIN = "example.com"


def test_aggregate_counts_issuers_and_window() -> None:
    result = aggregate_transparency(crt_payload(), domain=DOMAIN)

    # six fixture entries, one duplicate id -> five unique certificates
    assert result["count"] == 5
    assert result["issuers"] == [
        "C=US, O=DigiCert, CN=GlobalSign",
        "C=US, O=Let's Encrypt, CN=R3",
    ]
    assert result["first_seen"] == "2024-01-11T10:00:00"
    assert result["last_seen"] == "2024-05-15T16:20:00"


def test_aggregate_keeps_only_target_related_names() -> None:
    result = aggregate_transparency(crt_payload(), domain=DOMAIN)

    assert result["related_names"] == [
        "a.example.com",
        "b.example.com",
        "example.com",
        "rich.example.com",
        "www.example.com",
    ]
    assert "evil.other.test" not in result["related_names"]


def test_aggregate_orders_certificates_oldest_first() -> None:
    result = aggregate_transparency(crt_payload(), domain=DOMAIN)

    not_before = [cert["not_before"] for cert in result["certificates"]]
    assert not_before == sorted(not_before)
    assert result["certificates"][0]["common_name"] == "a.example.com"


def test_aggregate_deduplicates_by_id() -> None:
    entries = [*crt_payload(), crt_payload()[0]]

    result = aggregate_transparency(entries, domain=DOMAIN)

    assert result["count"] == 5


def test_aggregate_handles_empty_input() -> None:
    result = aggregate_transparency([], domain=DOMAIN)

    assert result["count"] == 0
    assert result["issuers"] == []
    assert result["certificates"] == []
    assert result["related_names"] == []
    assert result["first_seen"] == ""
    assert result["last_seen"] == ""


def test_aggregate_respects_max_results() -> None:
    result = aggregate_transparency(crt_payload(), domain=DOMAIN, max_results=2)

    assert result["count"] == 5
    assert len(result["certificates"]) == 2


async def test_fetch_transparency_uses_shared_http(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        CRT_URL, body=crt_payload(), headers={"content-type": "application/json"}
    )
    ctx = make_module_context(make_module_config(tmp_path), http=client)

    result = await fetch_transparency(CertificateModule(), ctx, DOMAIN)

    assert result["count"] == 5
    assert client.requests[0]["kwargs"]["params"] == {
        "q": "%.example.com",
        "output": "json",
    }


async def test_fetch_transparency_degrades_offline(tmp_path: Path) -> None:
    client = FakeHttpClient()  # no stub -> 404 -> HttpError
    ctx = make_module_context(make_module_config(tmp_path), http=client)

    result = await fetch_transparency(CertificateModule(), ctx, DOMAIN)

    assert result["count"] == 0


async def test_fetch_transparency_without_http_returns_empty(tmp_path: Path) -> None:
    ctx = make_module_context(make_module_config(tmp_path))

    result = await fetch_transparency(CertificateModule(), ctx, DOMAIN)

    assert result["count"] == 0
