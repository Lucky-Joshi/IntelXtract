"""DoH (Phase 8, S8.2) DNS module tests against recorded fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import Severity
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import doh_handler
from modules.domain.dns import DNS_TYPES, DnsModule

DOH_URL = "https://cloudflare-dns.com/dns-query"


async def test_dns_collects_records_spf_dmarc_dkim(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    client = FakeHttpClient()
    client.stub(DOH_URL, body=doh_handler())
    ctx = make_module_context(cfg, http=client)

    result = await DnsModule().run("example.com", ctx)

    data = result.data
    assert data["records"]["A"] == ["93.184.216.34"]
    assert data["records"]["AAAA"] == []
    assert data["records"]["NS"] == ["a.iana-servers.net.", "b.iana-servers.net."]
    assert data["records"]["MX"] == ["0 ."]
    assert data["spf"] and data["spf"].startswith("v=spf1")
    assert data["dmarc"] and data["dmarc"].startswith("v=DMARC1; p=none")
    assert data["dkim"] == {
        "s1": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDQe..."
    }

    titles = {f.title for f in result.findings}
    assert "DNS: A records" in titles
    assert "DNS: AAAA records" in titles
    assert "DNS: NS records" in titles
    assert "DNS: MX records" in titles
    assert "DNS: TXT records" in titles
    assert "DNS: CNAME records" not in titles
    assert "DNS: SPF record" in titles
    assert "DNS: DMARC record" in titles
    assert "DNS: DKIM selector 's1'" in titles
    assert not any(f.severity is Severity.HIGH for f in result.findings)


async def test_dns_probes_dmarc_and_dkim_selectors(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    client = FakeHttpClient()
    client.stub(DOH_URL, body=doh_handler())
    ctx = make_module_context(cfg, http=client)

    await DnsModule().run("example.com", ctx)

    probed: dict[str, dict[str, str]] = {}
    for request in client.requests:
        params = request["kwargs"].get("params") or {}
        key = (params.get("name") or "", params.get("type") or "")
        if key[0].startswith("_") or "_domainkey" in key[0]:
            probed[key[0]] = {
                "type": params["type"],
                "headers": request["kwargs"].get("headers", {}),
            }

    assert probed["_dmarc.example.com"]["type"] == "TXT"
    assert probed["_dmarc.example.com"]["headers"] == {"Accept": "application/dns-json"}
    assert "s1._domainkey.example.com" in probed
    assert "default._domainkey.example.com" in probed


async def test_dns_reports_missing_spf_and_dmarc(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    client = FakeHttpClient()

    def handler(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], object]:
        params = kwargs.get("params") or {}
        name = str(params.get("name", ""))
        dns_type = str(params.get("type", ""))
        if name == "example.com" and dns_type in DNS_TYPES:
            return 200, {}, {"Status": 0}
        return 200, {}, {"Status": 0}

    client.stub(DOH_URL, body=handler)
    ctx = make_module_context(cfg, http=client)

    result = await DnsModule().run("example.com", ctx)

    titles = {f.title for f in result.findings}
    assert "DNS: no SPF record" in titles
    assert "DNS: no DMARC record" in titles
    spf = next(f for f in result.findings if f.title == "DNS: no SPF record")
    dmarc = next(f for f in result.findings if f.title == "DNS: no DMARC record")
    assert spf.severity is Severity.LOW
    assert dmarc.severity is Severity.LOW
    data = result.data
    assert data["spf"] is None
    assert data["dmarc"] is None
