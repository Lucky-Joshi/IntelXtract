"""RSS/Atom parsing and fetching (Phase 15, S15.1/S15.4).

Parses RSS 2.0 and Atom 1.0 into a shared article record using only the
standard library; the Google News RSS bridge needs no API key.  Fetching
goes through the shared HTTP client so tests stub endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

from core.engine import ModuleContext
from modules.base import BaseModule

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


class FeedParseError(ValueError):
    """Raised when a payload is not well-formed XML we can read."""


def parse_date(value: str | None) -> str:
    """Normalize RFC 2822 or ISO-8601 date strings to UTC ISO-8601 seconds."""
    if not value or not str(value).strip():
        return ""
    raw = str(value).strip()
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        pass
    else:
        if parsed is not None:
            return _as_utc_iso(parsed)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return _as_utc_iso(parsed)


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _text(element: ElementTree.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _child(root: ElementTree.Element, *names: str) -> str:
    for namespace in (None, "{http://www.w3.org/2005/Atom}"):
        for name in names:
            element = root.find(f"{namespace or ''}{name}")
            if element is not None and (element.text or "").strip():
                return (element.text or "").strip()
    return ""


def _rss_items(root: ElementTree.Element) -> list[dict[str, Any]]:
    channel = root.find("channel")
    source = _child(channel, "title") if channel is not None else ""
    items: list[dict[str, Any]] = []
    for item in channel.findall("item") if channel is not None else []:
        items.append(
            {
                "title": _child(item, "title"),
                "url": _child(item, "link"),
                "source": _child(item, "source") or source,
                "published": parse_date(_child(item, "pubDate", "date")),
                "guid": _child(item, "guid"),
            }
        )
    return items


def _atom_items(root: ElementTree.Element) -> list[dict[str, Any]]:
    ns = "{http://www.w3.org/2005/Atom}"
    source = _child(root, "title")
    items: list[dict[str, Any]] = []
    for entry in root.findall(f"{ns}entry"):
        link = ""
        for candidate in entry.findall(f"{ns}link"):
            if (candidate.get("rel") or "alternate") == "alternate":
                link = candidate.get("href") or ""
                break
        items.append(
            {
                "title": _child(entry, "title"),
                "url": link,
                "source": source,
                "published": parse_date(_child(entry, "published", "updated")),
                "guid": _child(entry, "id"),
            }
        )
    return items


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """Parse RSS 2.0 or Atom 1.0 XML into article record dicts."""
    try:
        root = ElementTree.fromstring(  # noqa: S314 - external feeds, values only feed article fields
            xml_text
        )
    except ElementTree.ParseError as exc:
        raise FeedParseError(f"invalid feed XML: {exc}") from exc

    tag = root.tag
    if tag.endswith("rss") or tag == "rss":
        return _rss_items(root)
    if tag.endswith("feed"):
        return _atom_items(root)
    raise FeedParseError(f"unsupported root element {tag!r}")


def google_news_url(keyword: str) -> str:
    """Bare Google News RSS search URL (query params are added by the client)."""
    return GOOGLE_NEWS_RSS


async def fetch_feed(
    module: BaseModule, ctx: ModuleContext, url: str, keyword: str = ""
) -> list[dict[str, Any]]:
    """Fetch and parse one feed; never raises (degrades to no articles)."""
    try:
        if url == GOOGLE_NEWS_RSS:
            text = await module.http_get_text(
                ctx,
                url,
                params={"q": keyword, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            )
        else:
            text = await module.http_get_text(ctx, url)
    except Exception:
        return []
    try:
        return parse_feed(text)
    except FeedParseError:
        return []


__all__ = [
    "FeedParseError",
    "fetch_feed",
    "google_news_url",
    "parse_date",
    "parse_feed",
]
