"""HTTP method / title probes (Phase 10, S10.5) module tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import tech_html
from modules.website.http_methods import HttpMethodsModule

PAGE_URL = "https://example.com/"


def _method_handler(allowed: str, *, title: str, options_status: int = 200) -> Any:
    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], str]:
        if method == "OPTIONS":
            return options_status, {"Allow": allowed}, ""
        if method == "HEAD":
            return 200, {"Content-Type": "text/html; charset=utf-8"}, ""
        return 200, {"Content-Type": "text/html; charset=utf-8"}, tech_html()

    return _handle


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.URL)


async def test_http_methods_reports_allowed_trace_and_title(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        PAGE_URL, body=_method_handler("GET, HEAD, OPTIONS, TRACE", title="Acme Home")
    )
    ctx = _ctx(tmp_path, client=client)

    result = await HttpMethodsModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "ok"
    assert result.data["methods"] == ["GET", "HEAD", "OPTIONS", "TRACE"]
    assert result.data["title"] == "Acme Home"
    assert result.data["content_type"].startswith("text/html")

    titles = {f.title for f in result.findings}
    assert "HTTP: allowed methods" in titles
    assert "HTTP: TRACE enabled" in titles
    assert "HTTP: page title" in titles
    assert "HTTP: page profile" in titles

    trace = next(f for f in result.findings if f.title == "HTTP: TRACE enabled")
    assert trace.severity is Severity.MEDIUM


async def test_http_methods_restricted_options(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        PAGE_URL, body=_method_handler("", title="Acme Home", options_status=405)
    )
    ctx = _ctx(tmp_path, client=client)

    result = await HttpMethodsModule().run(PAGE_URL, ctx)

    assert result.data["methods"] == []
    assert "HTTP: OPTIONS restricted" in {f.title for f in result.findings}
    assert not any(f.title == "HTTP: TRACE enabled" for f in result.findings)
