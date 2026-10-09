"""Reverse DNS + forward-confirmed (Phase 9, S9.2) module tests."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, HttpError, make_module_config, make_module_context
from modules.ip._dns import dnsbl_name, reverse_name
from modules.ip.rdns import RdnsModule

DOH_URL = "https://cloudflare-dns.com/dns-query"

V4_REVERSE = "1.1.1.1.in-addr.arpa"
_V6_EXPANDED = ipaddress.ip_address("2001:db8::1").exploded.replace(":", "")
V6_REVERSE = ".".join(reversed(_V6_EXPANDED)) + ".ip6.arpa"


def _handler(
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


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.IP)


def test_reverse_and_dnsbl_names() -> None:
    assert reverse_name("1.1.1.1") == V4_REVERSE
    assert reverse_name("8.8.4.4") == "4.4.8.8.in-addr.arpa"
    assert reverse_name("2001:db8::1") == V6_REVERSE

    assert dnsbl_name("1.1.1.1", "zen.spamhaus.org") == "1.1.1.1.zen.spamhaus.org"
    assert dnsbl_name("2001:db8::1", "zen.spamhaus.org") is None


async def test_rdns_forward_confirmed(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        DOH_URL,
        body=_handler(
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
            }
        ),
    )
    ctx = _ctx(tmp_path, client=client)

    result = await RdnsModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "ok"
    assert result.data["reverse"] == ["one.one.one.one"]
    assert result.data["confirmed"] == ["one.one.one.one"]

    titles = {f.title for f in result.findings}
    assert "RDNS: PTR record" in titles
    assert "RDNS: forward-confirmed" in titles


async def test_rdns_forward_confirmation_mismatch_is_low(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        DOH_URL,
        body=_handler(
            {
                (V4_REVERSE, "PTR"): [
                    {
                        "name": V4_REVERSE,
                        "type": 12,
                        "TTL": 60,
                        "data": "web.example.com.",
                    }
                ],
                ("web.example.com", "A"): [
                    {
                        "name": "web.example.com",
                        "type": 1,
                        "TTL": 60,
                        "data": "192.0.2.5",
                    }
                ],
            }
        ),
    )
    ctx = _ctx(tmp_path, client=client)

    result = await RdnsModule().run("1.1.1.1", ctx)

    assert result.data["confirmed"] == []
    titles = {f.title for f in result.findings}
    assert "RDNS: PTR record" in titles
    assert "RDNS: forward-confirmation failed" in titles
    failed = next(f for f in result.findings if "forward-confirmation" in f.title)
    assert failed.severity is Severity.LOW


async def test_rdns_no_ptr_reports_low(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(DOH_URL, body=_handler({}))
    ctx = _ctx(tmp_path, client=client)

    result = await RdnsModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "no_record"
    assert result.data["reverse"] == []
    assert result.findings[0].title == "RDNS: no PTR record"
    assert result.findings[0].severity is Severity.LOW


async def test_rdns_ipv6_reverse_forward_confirmed(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        DOH_URL,
        body=_handler(
            {
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
    ctx = _ctx(tmp_path, client=client)

    result = await RdnsModule().run("2001:db8::1", ctx)

    assert result.data["state"] == "ok"
    assert result.data["confirmed"] == ["host.example.com"]
    assert "RDNS: forward-confirmed" in {f.title for f in result.findings}


async def test_rdns_offline_degrades_to_low_finding(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def refused(
        method: str, url: str, kwargs: dict
    ) -> tuple[int, dict[str, str], None]:
        raise HttpError(503, url)

    client.stub(DOH_URL, body=refused)
    ctx = _ctx(tmp_path, client=client)

    result = await RdnsModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "unavailable"
    assert result.findings[0].title == "RDNS: lookup unavailable"
    assert result.findings[0].severity is Severity.LOW
    assert result.findings[0].confidence <= 0.7
