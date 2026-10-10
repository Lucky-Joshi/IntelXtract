"""S12.2 — batch presence probing of username profile pages.

Conservative by design: a probe returns "exists", "missing", or "unknown";
anything that does not conclusively match a site's rule (redirects, bot
walls, 5xx, mismatches) resolves to ``unknown`` — never a false "not found".
Requests are bounded by a global concurrency semaphore and a per-site
minimum interval so public endpoints are paced.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

from core.engine import ModuleContext
from modules.username.sites import render_url

VERDICT_EXISTS = "exists"
VERDICT_MISSING = "missing"
VERDICT_UNKNOWN = "unknown"

_MAX_BODY_BYTES = 2_000_000


def _marker_hit(rule: Mapping[str, Any], body: str) -> str | None:
    for key in ("missing_marker", "exists_marker"):
        marker = rule.get(key) or ""
        if marker and marker in body:
            return marker
    return None


def _classify(rule: Mapping[str, Any], status: int | None, body: str) -> str:
    """Resolve a verdict from status codes plus optional body markers."""
    missing_marker = rule.get("missing_marker") or ""
    if missing_marker and missing_marker in body:
        return VERDICT_MISSING
    exists_marker = rule.get("exists_marker") or ""
    if exists_marker and exists_marker in body:
        return VERDICT_EXISTS
    if status is not None and status in rule.get("exists", []):
        return VERDICT_EXISTS
    if status is not None and status in rule.get("missing", []):
        return VERDICT_MISSING
    return VERDICT_UNKNOWN


async def probe_site(
    ctx: ModuleContext,
    site: Mapping[str, Any],
    username: str,
) -> dict[str, Any]:
    """Probe one site and return ``{name, url, verdict, status, marker_hit}``."""
    url = render_url(site, username)
    status: int | None = None
    body = ""
    if ctx.http is None:
        return _unknown(site, url, None, None)
    try:
        response = await ctx.http.request("GET", url, allow_redirects=True)
        status = response.status
        body = (response.body or b"")[:_MAX_BODY_BYTES].decode(
            "utf-8", errors="replace"
        )
    except Exception:
        status = None
        body = ""

    rule = site["rule"]
    verdict = _classify(rule, status, body)
    return {
        "name": site["name"],
        "url": url,
        "verdict": verdict,
        "status": status,
        "marker_hit": _marker_hit(rule, body),
    }


def _unknown(
    site: Mapping[str, Any],
    url: str,
    status: int | None,
    marker_hit: str | None,
) -> dict[str, Any]:
    return {
        "name": site["name"],
        "url": url,
        "verdict": VERDICT_UNKNOWN,
        "status": status,
        "marker_hit": marker_hit,
    }


class _PacedProbe:
    """Applies a global semaphore plus per-site spacing between requests."""

    def __init__(self, concurrency: int, per_site_interval: float) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._interval = per_site_interval
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def run(
        self,
        ctx: ModuleContext,
        sites: list[Any],
        username: str,
    ) -> list[dict[str, Any]]:
        async def one(site: Mapping[str, Any]) -> dict[str, Any]:
            name = site["name"]
            lock = self._locks.setdefault(name, asyncio.Lock())
            async with self._semaphore:
                async with lock:
                    await self._pace(name)
                    try:
                        return await probe_site(ctx, site, username)
                    finally:
                        self._last[name] = time.monotonic()

        results: list[dict[str, Any]] = []
        for future in asyncio.as_completed([one(site) for site in sites]):
            results.append(await future)
        return results

    async def _pace(self, name: str) -> None:
        since = self._last.get(name)
        if since is None:
            return
        elapsed = time.monotonic() - since
        if elapsed < self._interval:
            await asyncio.sleep(self._interval - elapsed)


async def check_sites(
    ctx: ModuleContext,
    sites: list[Any],
    username: str,
    *,
    concurrency: int = 8,
    per_site_interval: float = 1.0,
) -> list[dict[str, Any]]:
    """Probe all sites concurrently, paced per site, and return verdicts."""
    paced = _PacedProbe(max(1, int(concurrency)), max(0.0, per_site_interval))
    return await paced.run(ctx, sites, username)
