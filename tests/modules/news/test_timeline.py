"""News timeline builder tests (Phase 15, S15.3/S15.4)."""

from __future__ import annotations

from typing import Any

from modules.news.timeline import build_timeline, dedupe_articles


def _article(
    title: str,
    url: str,
    *,
    published: str = "",
    guid: str = "",
    source: str = "Wire",
) -> dict[str, Any]:
    return {
        "title": title,
        "url": url,
        "source": source,
        "published": published,
        "guid": guid,
    }


def test_dedupe_by_url_and_guid() -> None:
    articles = [
        _article(
            "First",
            "https://wire.example/a",
            published="2024-02-05T09:00:00+00:00",
            guid="g1",
        ),
        _article(
            "Same GUID",
            "https://wire.example/b",
            published="2024-02-05T10:00:00+00:00",
            guid="g1",
        ),
        _article(
            "Same URL",
            "https://wire.example/A/",
            published="2024-02-05T11:00:00+00:00",
            guid="g2",
        ),
        _article(
            "Unique",
            "https://wire.example/c",
            published="2024-02-05T12:00:00+00:00",
            guid="g3",
        ),
    ]

    unique = dedupe_articles(articles)

    assert [item["title"] for item in unique] == ["First", "Unique"]


def test_timeline_orders_newest_first_with_undated_last() -> None:
    articles = [
        _article(
            "Old", "https://wire.example/old", published="2024-01-01T00:00:00+00:00"
        ),
        _article(
            "New", "https://wire.example/new", published="2024-03-01T00:00:00+00:00"
        ),
        _article(
            "Mid", "https://wire.example/mid", published="2024-02-01T00:00:00+00:00"
        ),
        _article("Undated", "https://wire.example/undated"),
    ]

    timeline = build_timeline(articles)

    assert [item["title"] for item in timeline] == ["New", "Mid", "Old", "Undated"]


def test_timeline_caps_items() -> None:
    articles = [
        _article(
            f"Article {index}",
            f"https://wire.example/{index}",
            published=f"2024-01-{index + 1:02d}T00:00:00+00:00",
        )
        for index in range(20)
    ]

    timeline = build_timeline(articles, max_items=5)

    assert len(timeline) == 5
    assert timeline[0]["title"] == "Article 19"  # newest kept first


def test_build_timeline_handles_junk_input() -> None:
    assert build_timeline(None) == []
    assert build_timeline("not-a-list") == []
    assert build_timeline([{"title": "x", "url": None}]) == []
