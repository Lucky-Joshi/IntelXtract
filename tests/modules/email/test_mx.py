"""Phase 11 S11.2: MX presence, SPF/DMARC parsing, MX host resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.email.mx import mx_records, parse_dmarc, parse_spf, probe_mail_dns

DOH_URL = "https://cloudflare-dns.com/dns-query"


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


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.EMAIL)


def test_parse_spf_variants() -> None:
    parsed = parse_spf(
        [
            "v=spf1 include:_spf.google.com include:mail.example.com ~all",
            "unrelated txt",
        ]
    )
    assert parsed is not None
    assert parsed["include"] == ["_spf.google.com", "mail.example.com"]
    assert parsed["all"] == "~"

    hard = parse_spf(["v=spf1 -all"])
    assert hard is not None
    assert hard["all"] == "-"
    assert hard["include"] == []

    assert parse_spf(["no spf here", "google-site-verification=abc"]) is None


def test_parse_dmarc_variants() -> None:
    parsed = parse_dmarc(["v=DMARC1; p=reject; pct=100; rua=mailto:dmarc@example.com"])
    assert parsed is not None
    assert parsed["policy"] == "reject"
    assert parsed["percent"] == 100
    assert parsed["policy_note"]

    none = parse_dmarc(["v=DMARC1; p=none"])
    assert none is not None
    assert none["policy"] == "none"
    assert none["percent"] is None

    assert parse_dmarc(["v=spf1 -all"]) is None


async def test_mx_records_parse_and_resolve(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        DOH_URL,
        body=_doh_handler(
            {
                ("example.com", "MX"): [
                    {"data": "20 backup.example.com."},
                    {"data": "10 mail.example.com."},
                ],
                ("mail.example.com", "A"): [{"data": "203.0.113.10"}],
                ("backup.example.com", "A"): [{"data": "203.0.113.20"}],
            }
        ),
    )
    records = await mx_records(_ctx(tmp_path, client=client), DOH_URL, "example.com")
    assert [r["priority"] for r in records] == [10, 20]
    assert records[0]["host"] == "mail.example.com"
    assert records[0]["a"] == ["203.0.113.10"]


async def test_probe_mail_dns_missing_records(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(DOH_URL, body=_doh_handler({}))
    mail = await probe_mail_dns(_ctx(tmp_path, client=client), "nomx.example.com")
    assert mail["mx"] == []
    assert mail["spf"] is None
    assert mail["dmarc"] is None
