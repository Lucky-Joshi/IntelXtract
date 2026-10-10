"""News timeline builder (Phase 15, S15.3/S15.4).

Deduplicates aggregated articles by URL then GUID, orders the survivors
newest-first, and caps the list.  Pure and deterministic — the same input
always yields the same timeline, which the report phase can embed as-is.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


def _key(url: str) -> str:
    """Canonical identity of an article URL (fragment/query/hash stripped)."""
    if not url:
        return ""
    split = urlsplit(url.strip().lower())
    return f"{split.scheme}://{split.netloc}{split.path}".rstrip("/")


def _sort_key(article: dict[str, Any]) -> tuple[str, str]:
    published = str(article.get("published") or "")
    return ("0" if published else "", published)


def dedupe_articles(articles: Any) -> list[dict[str, Any]]:
    """Remove duplicate articles by URL/guid, keeping the first occurrence."""
    if not isinstance(articles, list):
        return []
    seen_urls: set[str] = set()
    seen_guids: set[str] = set()
    unique: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = _key(str(article.get("url") or ""))
        guid = str(article.get("guid") or "").strip().lower()
        if not url and not guid:
            continue  # no identity we can dedupe on
        if url and url in seen_urls:
            continue
        if guid and guid in seen_guids:
            continue
        if url:
            seen_urls.add(url)
        if guid:
            seen_guids.add(guid)
        unique.append(article)
    return unique


def build_timeline(articles: Any, *, max_items: int = 12) -> list[dict[str, Any]]:
    """Return deduplicated articles ordered newest-first, capped at ``max_items``."""
    unique = dedupe_articles(articles)
    unique.sort(key=_sort_key, reverse=True)
    return unique[:max_items]


__all__ = ["build_timeline", "dedupe_articles"]
