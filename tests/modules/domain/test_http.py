"""HTTP presence/security-header (Phase 8, S8.5) module tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.constants import Severity
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import http_handler
from modules.domain.http import _SECURITY_HEADERS, HttpProbeModule

HTTPS_URL = "https://example.com/"
HTTP_URL = "http://example.com/"
ROBOTS_URL = "https://example.com/robots.txt"
SITEMAP_URL = "https://example.com/sitemap.xml"


async def test_http_probe_reports_presence_and_headers(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    client = FakeHttpClient()
    client.stub(HTTPS_URL, body=http_handler())
    client.stub(HTTP_URL, body=http_handler())
    client.stub(ROBOTS_URL, body=http_handler())
    client.stub(SITEMAP_URL, body=http_handler())
    ctx = make_module_context(cfg, http=client)

    result = await HttpProbeModule().run("example.com", ctx)

    assert result.data["https"] == {
        "status": 301,
        "url": HTTPS_URL,
        "redirects": 0,
    }
    assert result.data["http"] == {"status": 301, "url": HTTP_URL, "redirects": 0}

    by_title = {f.title: f for f in result.findings}
    assert by_title["HTTP: https responds"].severity is Severity.INFO
    assert by_title["HTTP: http responds"].severity is Severity.INFO
    assert by_title["HTTP: redirect chain"].severity is Severity.LOW
    assert by_title["HTTP: robots.txt present"].severity is Severity.INFO
    assert by_title["HTTP: no sitemap.xml"].severity is Severity.LOW
    assert by_title["HTTP: strict-transport-security present"].severity is Severity.INFO
    assert by_title["HTTP: content-security-policy present"].severity is Severity.INFO
    assert (
        by_title["HTTP: missing x-frame-options"].severity
        is _SECURITY_HEADERS["x-frame-options"]
    )


async def test_http_probe_headers_case_insensitive(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    client = FakeHttpClient()

    def handler(
        method: str, url: str, kwargs: dict[str, object]
    ) -> tuple[int, dict[str, str], str]:
        if url == HTTPS_URL:
            return 200, {"Strict-Transport-Security": "max-age=100"}, "ok"
        return 200, {}, "ok"

    for url in (HTTPS_URL, HTTP_URL, ROBOTS_URL, SITEMAP_URL):
        client.stub(url, body=handler)
    ctx = make_module_context(cfg, http=client)

    result = await HttpProbeModule().run("example.com", ctx)
    titles = {f.title for f in result.findings}
    assert "HTTP: strict-transport-security present" in titles
    assert "HTTP: missing content-security-policy" in titles


async def test_http_probe_requires_context_http(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    ctx = make_module_context(cfg, http=None)

    with pytest.raises(RuntimeError):
        await HttpProbeModule().run("example.com", ctx)
