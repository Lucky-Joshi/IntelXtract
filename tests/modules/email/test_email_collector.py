"""Phase 11: EmailModule wiring (validation + mail DNS + Gravatar)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.email.collector import EmailModule

DOH_URL = "https://cloudflare-dns.com/dns-query"
GRAVATAR_URL = "https://www.gravatar.com/avatar/"
TARGET = "alice@example.com"


def _doh_handler(
    table: dict[tuple[str, str], Any],
) -> Any:
    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        params = kwargs.get("params") or {}
        query = (str(params.get("name", "")), str(params.get("type", "")))
        answers = table.get(query)
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


def _answers(*data: str) -> list[dict[str, str]]:
    return [{"data": value} for value in data]


def _doh_stub(
    client: FakeHttpClient,
    *,
    mx: list[str] | None = None,
    spf: list[str] | None = None,
    dmarc: list[str] | None = None,
) -> None:
    table: dict[tuple[str, str], Any] = {}
    if mx is not None:
        table[("example.com", "MX")] = _answers(*mx)
        table[("mail.example.com", "A")] = [{"data": "203.0.113.10"}]
    if spf is not None:
        table[("example.com", "TXT")] = _answers(*spf)
    if dmarc is not None:
        table[("_dmarc.example.com", "TXT")] = _answers(*dmarc)
    client.stub(DOH_URL, body=_doh_handler(table))


async def test_email_module_full_profile(tmp_path: Path) -> None:
    client = FakeHttpClient()
    _doh_stub(
        client,
        mx=["10 mail.example.com."],
        spf=['"v=spf1 include:_spf.example.com -all"'],
        dmarc=['"v=DMARC1; p=reject; pct=100"'],
    )
    result = await EmailModule().run(TARGET, _ctx(tmp_path, client=client))

    assert result.data["target"] == TARGET
    assert result.data["disposable"] is False
    assert result.data["mail"]["mx"][0]["host"] == "mail.example.com"
    assert result.data["mail"]["spf"]["all"] == "-"
    assert result.data["mail"]["dmarc"]["policy"] == "reject"
    assert result.data["gravatar"]["exists"] is False

    titles = {f.title for f in result.findings}
    assert "Email: MX records" in titles
    assert "Email: SPF policy" in titles
    assert "Email: DMARC policy" in titles
    spf = next(f for f in result.findings if f.title == "Email: SPF policy")
    assert spf.severity is Severity.INFO


async def test_email_module_no_mail_security(tmp_path: Path) -> None:
    client = FakeHttpClient()
    _doh_stub(client, mx=[], spf=[], dmarc=[])
    result = await EmailModule().run("bob@example.com", _ctx(tmp_path, client=client))

    titles = {f.title for f in result.findings}
    assert "Email: domain accepts no mail (no MX)" in titles
    assert "Email: no SPF record" in titles
    assert "Email: no DMARC record" in titles
    assert any(
        f.severity is Severity.MEDIUM
        for f in result.findings
        if f.title == "Email: domain accepts no mail (no MX)"
    )
    assert any(
        f.severity is Severity.LOW
        for f in result.findings
        if f.title == "Email: no SPF record"
    )


async def test_email_module_disposable_address(tmp_path: Path) -> None:
    client = FakeHttpClient()
    _doh_stub(
        client,
        mx=["10 mail.example.com."],
        spf=['"v=spf1 -all"'],
        dmarc=['"v=DMARC1; p=reject"'],
    )
    result = await EmailModule().run(
        "foo@mailinator.com", _ctx(tmp_path, client=client)
    )
    assert result.data["disposable"] is True
    assert any(
        f.title == "Email: disposable address" and f.severity is Severity.MEDIUM
        for f in result.findings
    )


async def test_email_module_degrades_on_dns_failure(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def _boom(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        raise RuntimeError("dns failed")

    client.stub(DOH_URL, body=_boom)
    result = await EmailModule().run(TARGET, _ctx(tmp_path, client=client))

    assert result.data["state"] == "degraded"
    assert result.data["mail"]["state"] == "unavailable"
    assert any(
        f.title == "Email: mail infrastructure check unavailable"
        and f.severity is Severity.LOW
        for f in result.findings
    )


async def test_email_module_invalid_target_at_run(tmp_path: Path) -> None:
    client = FakeHttpClient()
    result = await EmailModule().run("not-an-email", _ctx(tmp_path, client=client))
    assert result.data["state"] == "invalid"
    assert result.data["syntax"] is False
    assert any(f.title == "Email: malformed address" for f in result.findings)
