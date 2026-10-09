"""robots.txt + sitemap.xml extraction (Phase 10, S10.4).

Fetches ``/robots.txt`` (sharing the Phase 8-style non-raising fetch, so a
missing file is a normal ``404`` result) and parses it into user-agent groups
with allow/disallow/crawl-delay entries and advertised sitemap URLs.  The
sitemap (robots-declared or ``/sitemap.xml``) is then parsed for ``<loc>``
entries.  Nothing here relies on non-standard headers or JS rendering.
"""

from __future__ import annotations

import re
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.website._util import absolute

_SITEMAP_LOC = re.compile(
    r"<loc>(?:<!\[CDATA\[)?\s*([^<>\]]+?)\s*(?:\]\]>)?</loc>", re.I
)
_USER_AGENT_LINE = re.compile(r"^User-agent\s*:\s*(.+)$", re.I)
_DIRECTIVE_LINE = re.compile(r"^(Allow|Disallow|Crawl-delay|Sitemap)\s*:\s*(.*)$", re.I)


class RobotsModule(BaseModule):
    """robots.txt group parsing plus sitemap URL extraction."""

    name = "robots"
    target_types = (TargetType.URL,)
    description = "robots.txt groups and sitemap.xml URL extraction"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        robots_url = absolute(target, "/robots.txt")
        try:
            robots_response = await self.http_fetch(ctx, robots_url)
        except Exception as exc:
            return ModuleResult(
                data={"target": target, "state": "unavailable", "url": robots_url},
                findings=[
                    make_finding(
                        self.name,
                        "Robots: lookup unavailable",
                        {"target": target},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=str(exc),
                    )
                ],
                meta={"source": robots_url},
            )

        if robots_response.status >= 400:
            return ModuleResult(
                data={
                    "target": target,
                    "state": "missing",
                    "url": robots_url,
                    "status": robots_response.status,
                },
                findings=[
                    make_finding(
                        self.name,
                        "Robots: no robots.txt",
                        {"status": robots_response.status},
                        severity=Severity.LOW,
                        confidence=0.9,
                        evidence=f"HTTP {robots_response.status}",
                    )
                ],
                meta={"source": robots_url},
            )

        robots_text = robots_response.body.decode("utf-8", errors="replace")
        parsed = _parse_robots(robots_text)

        discovered = await _discover_sitemap_urls(self, ctx, target, parsed["sitemaps"])

        findings: list[Any] = [
            make_finding(
                self.name,
                "Robots: parsed robots.txt",
                {
                    "user_agents": parsed["user_agents"],
                    "groups": parsed["groups"],
                    "disallow": parsed["disallow"],
                    "max_disallow_depth": parsed["max_disallow_depth"],
                },
                severity=Severity.INFO,
                confidence=0.9,
                evidence=f"{parsed['groups']} group(s), "
                f"{len(parsed['disallow'])} disallow rule(s)",
            )
        ]
        if discovered:
            findings.append(
                make_finding(
                    self.name,
                    "Robots: sitemap URLs",
                    {"count": len(discovered), "urls": discovered[:8]},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"{len(discovered)} URL(s) in sitemap",
                )
            )

        data: dict[str, Any] = {
            "target": target,
            "state": "ok",
            "url": robots_url,
            "robots": parsed,
            "sitemap_urls": discovered,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": robots_url})


async def _discover_sitemap_urls(
    module: RobotsModule, ctx: ModuleContext, target: str, declared: list[str]
) -> list[str]:
    """Fetch robots-declared sitemaps plus ``/sitemap.xml`` and list URLs."""
    candidates = list(dict.fromkeys([*declared, absolute(target, "/sitemap.xml")]))
    discovered: list[str] = []
    for sitemap_url in candidates:
        try:
            response = await module.http_fetch(ctx, sitemap_url)
        except Exception:
            response = None
        if response is None or response.status >= 400:
            continue
        for value in _extract_locs(response.body.decode("utf-8", errors="replace")):
            if value not in discovered:
                discovered.append(value)
    return discovered


def _parse_robots(text: str) -> dict[str, Any]:
    """Parse robots.txt into groups plus a flat disallow list."""
    groups: dict[str, dict[str, Any]] = {}
    current: str | None = None

    def _ensure(group: str) -> None:
        nonlocal current
        if group not in groups:
            groups[group] = {"allow": [], "disallow": [], "crawl_delay": None}
        current = group

    sitemaps: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ua = _USER_AGENT_LINE.match(line)
        if ua:
            _ensure(ua.group(1).strip().lower() or "*")
            continue
        directive = _DIRECTIVE_LINE.match(line)
        if not directive:
            continue
        kind, value = directive.group(1).lower(), directive.group(2).strip()
        if kind == "sitemap":
            sitemaps.append(value)
        elif current is not None:
            entry = groups[current]
            if kind == "allow":
                entry["allow"].append(value)
            elif kind == "disallow":
                entry["disallow"].append(value)
            elif kind == "crawl-delay":
                entry["crawl_delay"] = value

    disallow = sorted({path for group in groups.values() for path in group["disallow"]})
    depths = [len([p for p in path.split("/") if p]) for path in disallow] or [0]
    return {
        "user_agents": sorted(groups),
        "groups": len(groups),
        "allow": sorted({p for g in groups.values() for p in g["allow"]}),
        "disallow": disallow,
        "max_disallow_depth": max(depths),
        "sitemaps": sitemaps,
    }


def _extract_locs(xml_text: str) -> list[str]:
    """Extract ``<loc>`` values from a sitemap or sitemap index."""
    seen: list[str] = []
    for match in _SITEMAP_LOC.finditer(xml_text):
        value = match.group(1).strip()
        if value and value not in seen:
            seen.append(value)
    return seen
