"""Configured RSS/Atom feed lists (Phase 15, S15.2).

Feeds can be configured three ways — always-on ``news.feeds`` entries, a
per-keyword map under ``news.feeds_by_domain`` (for case/domain-specific
sources), and runtime ``news.feeds_extra`` additions.  All three are merged
for a keyword and deduplicated by URL.
"""

from __future__ import annotations

from typing import Any

from modules.news.rss import GOOGLE_NEWS_RSS


def _clean_urls(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    urls: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            urls.append(value.strip().rstrip("/"))
    return urls


def load_feed_list(
    config: Any, keyword: str, *, include_google: bool = True
) -> list[str]:
    """Return the ordered feed URLs to check for ``keyword`` (deduplicated)."""
    urls: list[str] = []
    global_feeds = (
        _clean_urls(config.get("news.feeds", [])) if config is not None else []
    )
    domain_map = config.get("news.feeds_by_domain", {}) if config is not None else {}
    extra = (
        _clean_urls(config.get("news.feeds_extra", [])) if config is not None else []
    )

    by_keyword: list[str] = []
    if isinstance(domain_map, dict):
        for key, value in domain_map.items():
            if str(key) and keyword.startswith(str(key)):
                by_keyword.extend(_clean_urls(value))

    urls.extend(global_feeds)
    urls.extend(by_keyword)
    urls.extend(extra)
    if include_google:
        urls.insert(0, GOOGLE_NEWS_RSS)

    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url and url not in seen:
            unique.append(url)
            seen.add(url)
    return unique


__all__ = ["load_feed_list"]
