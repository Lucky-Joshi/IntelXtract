"""Phase 11 S11.4: key-gated HIBP breach module."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.email.breach import BreachModule

TARGET = "alice@example.com"
BREACH_URL = (
    "https://haveibeenpwned.com/api/v3/breachedaccount/"
    f"{quote(TARGET, safe='')}?truncateResponse=false"
)


def _ctx(
    tmp_path: Path, *, client: FakeHttpClient, secret: str | None
) -> ModuleContext:
    cfg = make_module_config(tmp_path, key="hibp", secret=secret)
    return make_module_context(cfg, http=client, target_type=TargetType.EMAIL)


def test_breach_requires_hibp_key() -> None:
    module = BreachModule()
    assert module.name == "breach"
    assert module.requires_keys == ("hibp",)
    assert module.target_types == (TargetType.EMAIL,)


async def test_breach_found(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        BREACH_URL,
        status=200,
        body='[{"Name": "Adobe"}, {"Name": "LinkedIn"}]',
    )
    result = await BreachModule().run(
        TARGET, _ctx(tmp_path, client=client, secret="unit-test-key")
    )
    assert result.data["state"] == "ok"
    assert result.data["count"] == 2
    assert result.data["breaches"] == ["Adobe", "LinkedIn"]
    assert any(
        f.severity is Severity.HIGH
        for f in result.findings
        if f.title == "Breach: address exposed in known breach(es)"
    )

    request = client.requests[0]
    headers = request["kwargs"].get("headers") or {}
    assert headers["hibp-api-key"] == "unit-test-key"
    assert "user-agent" in headers


async def test_breach_not_found(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(BREACH_URL, status=404, body="")
    result = await BreachModule().run(
        TARGET, _ctx(tmp_path, client=client, secret="unit-test-key")
    )
    assert result.data["state"] == "ok"
    assert result.data["breaches"] == []
    assert any(f.title == "Breach: no known breaches" for f in result.findings)


async def test_breach_key_rejected(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(BREACH_URL, status=401, body="")
    result = await BreachModule().run(
        TARGET, _ctx(tmp_path, client=client, secret="unit-test-key")
    )
    assert result.data["state"] == "unauthorized"
    assert any(
        f.severity is Severity.MEDIUM
        for f in result.findings
        if f.title == "Breach: API key rejected"
    )


async def test_breach_unexpected_status_degrades(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(BREACH_URL, status=503, body="")
    result = await BreachModule().run(
        TARGET, _ctx(tmp_path, client=client, secret="unit-test-key")
    )
    assert result.data["state"] == "degraded"
    assert any(f.title == "Breach: unexpected API response" for f in result.findings)


async def test_breach_transport_error(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def _boom(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        raise RuntimeError("connection refused")

    client.stub(BREACH_URL, body=_boom)
    result = await BreachModule().run(
        TARGET, _ctx(tmp_path, client=client, secret="unit-test-key")
    )
    assert result.data["state"] == "unavailable"
    assert any(f.title == "Breach: check unavailable" for f in result.findings)
