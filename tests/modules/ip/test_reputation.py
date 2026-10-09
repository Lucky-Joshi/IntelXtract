"""Spamhaus ZEN + optional AbuseIPDB (Phase 9, S9.3) reputation tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, HttpError, make_module_config, make_module_context
from modules.ip.reputation import ReputationModule

DOH_URL = "https://cloudflare-dns.com/dns-query"
ZEN_QUERY = "1.1.1.1.zen.spamhaus.org"
ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"


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


def _ctx(
    tmp_path: Path, *, client: FakeHttpClient, key: str | None = None
) -> ModuleContext:
    cfg = make_module_config(tmp_path, key="abuseipdb", secret=key)
    return make_module_context(cfg, http=client, target_type=TargetType.IP)


async def test_reputation_dnsbl_clean(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(DOH_URL, body=_doh_handler({}))
    ctx = _ctx(tmp_path, client=client)

    result = await ReputationModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "ok"
    assert result.data["dnsbl"]["listed"] is False
    assert result.data["dnsbl"]["records"] == []
    assert result.data["abuseipdb"]["state"] == "no_key"
    assert "Reputation: DNSBL clean" in {f.title for f in result.findings}


async def test_reputation_dnsbl_listing_is_high(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        DOH_URL,
        body=_doh_handler(
            {
                (ZEN_QUERY, "A"): [
                    {"name": ZEN_QUERY, "type": 1, "TTL": 60, "data": "127.0.0.10"}
                ]
            }
        ),
    )
    ctx = _ctx(tmp_path, client=client)

    result = await ReputationModule().run("1.1.1.1", ctx)

    assert result.data["dnsbl"]["listed"] is True
    listing = next(f for f in result.findings if f.title == "Reputation: DNSBL listing")
    assert listing.severity is Severity.HIGH
    assert listing.data["records"][0]["code"] == "PBL"


async def test_reputation_ipv6_out_of_scope_never_queries(tmp_path: Path) -> None:
    client = FakeHttpClient()
    ctx = _ctx(tmp_path, client=client)

    result = await ReputationModule().run("2001:db8::1", ctx)

    assert result.data["state"] == "ok"
    assert result.data["dnsbl"]["state"] == "skipped"
    assert len(client.requests) == 0
    assert "Reputation: IPv6 out of scope for DNSBL" in {
        f.title for f in result.findings
    }


async def test_reputation_abuseipdb_reports_abuse_when_keyed(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(DOH_URL, body=_doh_handler({}))
    client.stub(
        ABUSEIPDB_URL,
        body={
            "data": {
                "ipAddress": "1.1.1.1",
                "isWhitelisted": False,
                "abuseConfidenceScore": 100,
                "countryCode": "US",
                "usageType": "Web hosting",
            }
        },
    )
    ctx = _ctx(tmp_path, client=client, key="test-key-1234")

    result = await ReputationModule().run("1.1.1.1", ctx)

    abusive = next(
        f for f in result.findings if f.title == "Reputation: AbuseIPDB abusive"
    )
    assert abusive.severity is Severity.HIGH
    assert abusive.data["score"] == 100
    assert result.data["abuseipdb"]["state"] == "ok"

    request = next(r for r in client.requests if r["url"] == ABUSEIPDB_URL)
    assert request["kwargs"]["headers"]["Key"] == "test-key-1234"
    assert request["kwargs"]["params"]["ipAddress"] == "1.1.1.1"


async def test_reputation_abuseipdb_clean_is_info(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(DOH_URL, body=_doh_handler({}))
    client.stub(
        ABUSEIPDB_URL,
        body={
            "data": {
                "ipAddress": "1.1.1.1",
                "isWhitelisted": False,
                "abuseConfidenceScore": 0,
                "countryCode": "US",
            }
        },
    )
    ctx = _ctx(tmp_path, client=client, key="test-key-1234")

    result = await ReputationModule().run("1.1.1.1", ctx)

    clean = next(f for f in result.findings if f.title == "Reputation: AbuseIPDB clean")
    assert clean.severity is Severity.INFO


async def test_reputation_degrades_when_source_unavailable(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def refused(
        method: str, url: str, kwargs: dict
    ) -> tuple[int, dict[str, str], None]:
        raise HttpError(503, url)

    client.stub(DOH_URL, body=refused)
    ctx = _ctx(tmp_path, client=client)

    result = await ReputationModule().run("1.1.1.1", ctx)

    assert result.data["state"] == "degraded"
    assert result.data["dnsbl"]["state"] == "unavailable"
    degraded = next(
        f for f in result.findings if f.title == "Reputation: DNSBL check unavailable"
    )
    assert degraded.severity is Severity.LOW
