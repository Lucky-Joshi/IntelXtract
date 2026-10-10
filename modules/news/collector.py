"""News module collector (Phase 15, S15.1-S15.4).

Runs a public Google News RSS search for the target domain and any
configured case-specific feeds, then builds a deduplicated newest-first
timeline.  Every feed fetch degrades to "no articles" on failure so an
offline scan never crashes.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.news.feeds import load_feed_list
from modules.news.rss import fetch_feed
from modules.news.timeline import build_timeline


class NewsModule(BaseModule):
    """Recent news/press mentions for a domain via public RSS search."""

    name = "news"
    target_types = (TargetType.DOMAIN,)
    description = "recent news timeline from Google News RSS and configured feeds"
    timeout = 30.0

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        max_items = int(ctx.config.get("news.max_items", 12))
        feeds = load_feed_list(ctx.config, target)

        articles_by_feed: list[dict[str, Any]] = []
        for url in feeds:
            articles_by_feed.extend(await fetch_feed(self, ctx, url, keyword=target))
        timeline = build_timeline(articles_by_feed, max_items=max_items)

        if not timeline:
            finding = make_finding(
                self.name,
                "News: no recent articles found",
                {"target": target, "count": 0},
                severity=Severity.LOW,
                confidence=0.5,
                evidence="all feeds returned nothing or failed",
            )
            return ModuleResult(
                data={
                    "target": target,
                    "state": "unavailable",
                    "count": 0,
                    "articles": [],
                },
                findings=[finding],
            )

        finding = make_finding(
            self.name,
            "News: timeline",
            {
                "target": target,
                "count": len(timeline),
                "articles": timeline,
            },
            severity=Severity.INFO,
            confidence=0.7,
            evidence=f"{len(timeline)} recent article(s) across {len(feeds)} feed(s)",
        )
        return ModuleResult(
            data={
                "target": target,
                "state": "ok",
                "count": len(timeline),
                "articles": timeline,
            },
            findings=[finding],
            meta={"feeds": len(feeds)},
        )


__all__ = ["NewsModule"]
