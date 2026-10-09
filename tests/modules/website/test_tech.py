"""Tech-stack detection (Phase 10, S10.2) module tests."""

from __future__ import annotations

from pathlib import Path

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import tech_html
from modules.website.tech_stack import TechStackModule

PAGE_URL = "https://example.com/"


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.URL)


async def test_tech_stack_detects_from_headers_cookies_and_html(
    tmp_path: Path,
) -> None:
    client = FakeHttpClient()
    client.stub(
        PAGE_URL,
        body=tech_html(),
        headers={
            "Server": "nginx",
            "X-Powered-By": "PHP/7.4",
            "Set-Cookie": "csrftoken=abc123; Path=/",
        },
    )
    ctx = _ctx(tmp_path, client=client)

    result = await TechStackModule().run(PAGE_URL, ctx)

    technologies = set(result.data["technologies"])
    assert {"nginx", "WordPress", "jQuery", "Bootstrap", "Django"} <= technologies

    titles = {f.title for f in result.findings}
    assert "Tech: nginx" in titles
    assert "Tech: WordPress" in titles
    assert "Tech: Django" in titles
    assert all(f.severity is Severity.INFO for f in result.findings)

    wp = next(f for f in result.findings if f.title == "Tech: WordPress")
    assert "wp-content" in wp.evidence
    nginx = next(f for f in result.findings if f.title == "Tech: nginx")
    assert nginx.evidence.startswith("header server:")
    django = next(f for f in result.findings if f.title == "Tech: Django")
    assert django.evidence == "cookie csrftoken present"


async def test_tech_stack_reports_empty_rule_corpus(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        PAGE_URL,
        body="<html><head><title>Plain</title></head><body>ok</body></html>",
        headers={"Server": "nginx"},
    )
    ctx = _ctx(tmp_path, client=client)

    result = await TechStackModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "ok"
    assert result.data["technologies"] == ["nginx"]
    assert [f.title for f in result.findings] == ["Tech: nginx"]
