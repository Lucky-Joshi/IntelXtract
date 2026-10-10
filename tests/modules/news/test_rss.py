"""RSS/Atom parsing + date normalization tests (Phase 15, S15.1/S15.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.engine import ModuleContext
from core.models import ModuleResult
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.base import BaseModule
from modules.news.rss import (
    GOOGLE_NEWS_RSS,
    FeedParseError,
    fetch_feed,
    parse_date,
    parse_feed,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "news"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_date_variants() -> None:
    assert parse_date("Mon, 02 Jan 2024 12:34:56 GMT") == "2024-01-02T12:34:56+00:00"
    assert parse_date("2024-01-02T12:34:56Z") == "2024-01-02T12:34:56+00:00"
    assert parse_date("2024-01-02T12:34:56+02:00") == "2024-01-02T10:34:56+00:00"
    assert parse_date(None) == ""
    assert parse_date("") == ""
    assert parse_date("  ") == ""
    assert parse_date("garbage-date") == ""


def test_rss_feed_parses_items() -> None:
    items = parse_feed(_read("feed.xml"))

    assert len(items) == 4
    first = items[0]
    assert first["title"] == "Breach at example.com"
    assert first["url"] == "https://security.example/breach.html"
    assert first["source"] == "SecurityWire"
    assert first["published"] == "2024-02-05T09:00:00+00:00"
    assert first["guid"] == "sec-1"

    patched = next(item for item in items if item["title"] == "example.com patched")
    assert patched["source"] == "SecurityWire"  # channel title fallback
    undated = next(item for item in items if item["title"] == "Undated notice")
    assert undated["published"] == ""


def test_atom_feed_parses_entries() -> None:
    items = parse_feed(_read("atom.xml"))

    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Example outage reported"
    assert first["url"] == "https://monitor.example/outage"
    assert first["source"] == "Example Monitor"
    assert first["published"] == "2024-06-01T08:00:00+00:00"
    assert first["guid"] == "atom-1"

    second = items[1]
    assert second["published"] == "2024-06-02T08:00:00+00:00"  # updated fallback


def test_malformed_feed_raises() -> None:
    with pytest.raises(FeedParseError):
        parse_feed(_read("malformed.xml"))


def test_unsupported_root_raises() -> None:
    with pytest.raises(FeedParseError):
        parse_feed("<html><body>hi</body></html>")


async def test_fetch_google_news_sends_keyword(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(GOOGLE_NEWS_RSS, body=_read("feed.xml"))
    ctx = make_module_context(make_module_config(tmp_path), http=client)
    module = _DummyModule()

    articles = await fetch_feed(module, ctx, GOOGLE_NEWS_RSS, keyword="example.com")

    assert len(articles) == 4
    request = client.requests[-1]
    assert request["kwargs"]["params"]["q"] == "example.com"
    assert request["kwargs"]["params"]["hl"] == "en-US"


async def test_fetch_feed_degrades_offline(tmp_path: Path) -> None:
    client = FakeHttpClient()  # 404 for everything
    ctx = make_module_context(make_module_config(tmp_path), http=client)

    articles = await fetch_feed(_DummyModule(), ctx, "https://feed.local/x")

    assert articles == []


async def test_fetch_feed_degrades_on_bad_xml(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://feed.local/bad", body="<broken")
    ctx = make_module_context(make_module_config(tmp_path), http=client)

    articles = await fetch_feed(_DummyModule(), ctx, "https://feed.local/bad")

    assert articles == []


class _DummyModule(BaseModule):
    """Minimal collector to satisfy ``fetch_feed``'s BaseModule typing."""

    name = "news-dummy"
    target_types = ()

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        return ModuleResult()
