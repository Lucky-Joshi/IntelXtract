"""Feed-list configuration tests (Phase 15, S15.2)."""

from __future__ import annotations

from core.config import Config
from modules.news.feeds import load_feed_list
from modules.news.rss import GOOGLE_NEWS_RSS


def _config_with_maps(
    *,
    feeds: list[str] | None = None,
    by_domain: dict[str, list[str]] | None = None,
    extra: list[str] | None = None,
) -> Config:
    config = Config(use_env=False)
    if feeds:
        config.set("news.feeds", feeds)
    if by_domain:
        config.set("news.feeds_by_domain", by_domain)
    if extra:
        config.set("news.feeds_extra", extra)
    return config


def test_google_news_is_always_first() -> None:
    urls = load_feed_list(Config(use_env=False), "example.com")

    assert urls == [GOOGLE_NEWS_RSS]


def test_merges_global_domain_and_extra_feed_sources() -> None:
    config = _config_with_maps(
        feeds=["https://global.example/feed"],
        by_domain={
            "example.com": ["https://case.example/feed"],
            "example.org": ["https://other.example/feed"],
        },
        extra=["https://extra.example/feed"],
    )

    urls = load_feed_list(config, "example.com")

    assert urls == [
        GOOGLE_NEWS_RSS,
        "https://global.example/feed",
        "https://case.example/feed",
        "https://extra.example/feed",
    ]


def test_matches_domain_by_substring_prefix() -> None:
    config = _config_with_maps(by_domain={"example.": ["https://tld.example/feed"]})

    urls = load_feed_list(config, "example.com")

    assert "https://tld.example/feed" in urls
    assert "https://tld.example/feed" not in load_feed_list(config, "other.tld")


def test_deduplicates_sources() -> None:
    config = _config_with_maps(
        feeds=["https://global.example/feed"],
        extra=["https://global.example/feed/"],  # trailing slash normalized
    )

    urls = load_feed_list(config, "example.com")

    assert urls.count("https://global.example/feed") == 1


def test_ignores_non_http_entries() -> None:
    config = _config_with_maps(feeds=["not-a-url", "ftp://files.example/feed"])

    urls = load_feed_list(config, "example.com")

    assert urls == [GOOGLE_NEWS_RSS]


def test_google_can_be_disabled() -> None:
    config = _config_with_maps(feeds=["https://global.example/feed"])

    urls = load_feed_list(config, "example.com", include_google=False)

    assert urls == ["https://global.example/feed"]
