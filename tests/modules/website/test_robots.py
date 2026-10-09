"""robots.txt + sitemap extraction (Phase 10, S10.4) module tests."""

from __future__ import annotations

from pathlib import Path

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import robots_txt, sitemap_xml
from modules.website.robots import RobotsModule, _extract_locs, _parse_robots

PAGE_URL = "https://example.com/"
ROBOTS_URL = "https://example.com/robots.txt"
SITEMAP_URL = "https://example.com/sitemap.xml"


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.URL)


def test_parse_robots_groups_and_depths() -> None:
    parsed = _parse_robots(robots_txt())
    assert parsed["user_agents"] == ["*"]
    assert parsed["groups"] == 1
    assert parsed["disallow"] == ["/admin/", "/private/passwords.txt"]
    assert parsed["allow"] == ["/public/"]
    assert parsed["max_disallow_depth"] == 2
    assert parsed["sitemaps"] == ["https://example.com/sitemap.xml"]


def test_extract_locs_parses_urlset() -> None:
    urls = _extract_locs(sitemap_xml())
    assert len(urls) == 3
    assert urls[0] == "https://example.com/"


async def test_robots_parses_and_lists_sitemap_urls(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(ROBOTS_URL, body=robots_txt())
    client.stub(SITEMAP_URL, body=sitemap_xml())
    ctx = _ctx(tmp_path, client=client)

    result = await RobotsModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "ok"
    assert result.data["robots"]["groups"] == 1
    assert result.data["robots"]["max_disallow_depth"] == 2
    assert len(result.data["sitemap_urls"]) == 3

    titles = {f.title for f in result.findings}
    assert "Robots: parsed robots.txt" in titles
    assert "Robots: sitemap URLs" in titles
    sitemap = next(f for f in result.findings if f.title == "Robots: sitemap URLs")
    assert sitemap.data["count"] == 3


async def test_robots_missing_reports_low(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(ROBOTS_URL, body=None, status=404)
    ctx = _ctx(tmp_path, client=client)

    result = await RobotsModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "missing"
    assert result.findings[0].title == "Robots: no robots.txt"
    assert result.findings[0].severity is Severity.LOW
