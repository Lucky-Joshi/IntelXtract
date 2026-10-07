"""RDAP (Phase 8, S8.1) WHOIS module tests against recorded fixtures."""

from __future__ import annotations

from pathlib import Path

from core.constants import Severity
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import rdap_payload
from modules.domain.whois import WhoisModule

RDAP_URL = "https://rdap.org/domain/example.com"


def _context(
    path: Path, *, redact: bool = True
) -> tuple[FakeHttpClient, ModuleContext]:
    cfg = make_module_config(path)
    cfg.set("whois.redact_emails", redact)
    client = FakeHttpClient()
    return client, make_module_context(cfg, http=client)


async def test_whois_extracts_facts(tmp_path: Path) -> None:
    client, ctx = _context(tmp_path)
    client.stub(
        RDAP_URL, body=rdap_payload(), headers={"content-type": "application/json"}
    )

    result = await WhoisModule().run("example.com", ctx)

    data = result.data
    assert data["registrar"] == "RESERVED-Internet Assigned Numbers Authority"
    assert data["dates"]["registration"] == "1995-08-14T04:00:00Z"
    assert data["dates"]["expiration"] == "2027-08-13T04:00:00Z"
    assert data["nameservers"] == ["a.iana-servers.net", "b.iana-servers.net"]
    assert data["status"] == ["client delete prohibited", "client transfer prohibited"]
    assert data["dnssec"] == {"delegation_signed": True}

    titles = {f.title for f in result.findings}
    assert "RDAP: registrar" in titles
    assert "RDAP: registration dates" in titles
    assert "RDAP: nameservers" in titles
    assert "RDAP: status flags" in titles
    assert "RDAP: DNSSEC signed" in titles
    assert "RDAP: registrant contact" in titles
    assert "RDAP: abuse contact" in titles
    assert not any(f.severity is Severity.HIGH for f in result.findings)


async def test_whois_redacts_emails_by_default(tmp_path: Path) -> None:
    client, ctx = _context(tmp_path)
    client.stub(RDAP_URL, body=rdap_payload())

    result = await WhoisModule().run("example.com", ctx)
    contacts = result.data["contacts"]
    assert contacts == [
        {
            "role": "registrant",
            "org": "Internet Corporation for Assigned Names and Numbers",
            "email": "***@iana.org",
        },
        {"role": "abuse", "org": "Domain Administrator", "email": "***@iana.org"},
    ]


async def test_whois_emails_kept_when_redaction_disabled(tmp_path: Path) -> None:
    client, ctx = _context(tmp_path, redact=False)
    client.stub(RDAP_URL, body=rdap_payload())

    result = await WhoisModule().run("example.com", ctx)
    emails = {c["email"] for c in result.data["contacts"]}
    assert emails == {"hostmaster@iana.org", "abuse@iana.org"}


async def test_whois_dnssec_not_signed(tmp_path: Path) -> None:
    client, ctx = _context(tmp_path)
    payload = rdap_payload()
    payload.pop("secureDNS", None)
    client.stub(RDAP_URL, body=payload)

    result = await WhoisModule().run("example.com", ctx)
    assert result.data["dnssec"] == {"delegation_signed": False}
    dnssec = next(f for f in result.findings if f.title.startswith("RDAP: DNSSEC"))
    assert dnssec.title == "RDAP: DNSSEC not signed"
    assert dnssec.severity is Severity.LOW
