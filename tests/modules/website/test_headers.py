"""Response-header profiling (Phase 10, S10.1) module tests."""

from __future__ import annotations

from pathlib import Path

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, HttpError, make_module_config, make_module_context
from modules.website.headers import HeadersModule, _parse_cookies

PAGE_URL = "https://example.com/"

FULL_HEADERS = {
    "Server": "nginx",
    "X-Powered-By": "PHP/7.4",
    "Content-Type": "text/html; charset=utf-8",
    "Content-Encoding": "gzip",
    "Strict-Transport-Security": "max-age=63072000",
    "Content-Security-Policy": "default-src 'self'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=()",
    "Set-Cookie": (
        "session=abc123; Path=/; HttpOnly; Secure; SameSite=Lax, " "lang=en; Path=/"
    ),
}

MINIMAL_HEADERS = {"Server": "nginx", "Set-Cookie": "sess=1; Path=/"}


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.URL)


def test_cookie_parsing() -> None:
    cookies = _parse_cookies(FULL_HEADERS["Set-Cookie"])
    assert [c["name"] for c in cookies] == ["session", "lang"]
    assert {"httponly", "secure", "samesite"} <= set(cookies[0]["flags"])
    assert cookies[1]["flags"] == ["path"]


async def test_headers_profiles_disclosure_security_and_cookies(
    tmp_path: Path,
) -> None:
    client = FakeHttpClient()
    client.stub(PAGE_URL, body="<html></html>", headers=FULL_HEADERS)
    ctx = _ctx(tmp_path, client=client)

    result = await HeadersModule().run(PAGE_URL, ctx)

    data = result.data
    assert data["state"] == "ok"
    assert data["server"] == "nginx"
    assert data["x_powered_by"] == "PHP/7.4"
    assert data["compression"] == "gzip"
    assert data["security"]["content-security-policy"] is True
    assert data["security"]["permissions-policy"] is True
    assert data["cookies"][1]["name"] == "lang"

    titles = {f.title for f in result.findings}
    assert "Headers: server disclosure" in titles
    assert "Headers: content-security-policy present" in titles
    assert "Headers: response compression" in titles
    assert "Headers: insecure cookie" in titles
    assert "Headers: response profile" in titles

    disclosure = next(
        f for f in result.findings if f.title == "Headers: server disclosure"
    )
    assert disclosure.severity is Severity.MEDIUM
    insecure = next(f for f in result.findings if f.title == "Headers: insecure cookie")
    assert insecure.data["cookie"] == "lang"
    assert insecure.severity is Severity.MEDIUM  # Secure flag missing


async def test_missing_security_headers_and_insecure_session_cookie(
    tmp_path: Path,
) -> None:
    client = FakeHttpClient()
    client.stub(PAGE_URL, body="<html></html>", headers=MINIMAL_HEADERS)
    ctx = _ctx(tmp_path, client=client)

    result = await HeadersModule().run(PAGE_URL, ctx)

    titles = {f.title for f in result.findings}
    assert "Headers: strict-transport-security missing" in titles
    assert "Headers: content-security-policy missing" in titles
    insecure = next(f for f in result.findings if f.title == "Headers: insecure cookie")
    assert set(insecure.data["missing"]) == {"Secure", "HttpOnly", "SameSite"}
    assert insecure.severity is Severity.MEDIUM


async def test_headers_offline_degrades_to_low_finding(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def refused(
        method: str, url: str, kwargs: dict
    ) -> tuple[int, dict[str, str], None]:
        raise HttpError(503, url)

    client.stub(PAGE_URL, body=refused)
    ctx = _ctx(tmp_path, client=client)

    result = await HeadersModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "unavailable"
    assert result.findings[0].title == "Headers: lookup unavailable"
    assert result.findings[0].severity is Severity.LOW
