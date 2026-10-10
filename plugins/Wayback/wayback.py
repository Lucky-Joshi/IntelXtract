"""Wayback Machine CDX plugin — living reference for the Plugin SDK (Phase 20).

Queries the public Web Archive CDX API for captures of a domain and reports
the archive span. No API key is required, so this plugin runs through the same
engine pipeline as core collectors with nothing but network access.

See ``docs/plugin_sdk.md`` for the full contract.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from core.plugin_loader import PluginBase

CDX_URL = "https://web.archive.org/cdx/search/cdx"
MAX_CAPTURES = 200


class WaybackPlugin(PluginBase):
    """Report the Wayback Machine capture history for a domain."""

    name = "wayback"
    version = "1.0.0"
    author = "IntelXtract"
    description = "Wayback Machine CDX archive history for a domain."
    target_types = (TargetType.DOMAIN,)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        try:
            rows = await ctx.http.get_json(
                CDX_URL,
                params={
                    "url": target,
                    "output": "json",
                    "collapse": "timestamp:6",
                    "limit": str(MAX_CAPTURES),
                    "fl": "timestamp,original,statuscode",
                },
            )
        except Exception as exc:  # network/HTTP failures are non-fatal
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "Wayback: archive lookup unavailable",
                        {"target": target, "error": str(exc)},
                        severity=Severity.INFO,
                        confidence=0.3,
                        evidence=f"CDX request failed: {exc}",
                    ),
                )
            )

        captures = _captures(rows)
        if not captures:
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "Wayback: no archived captures",
                        {"target": target},
                        severity=Severity.INFO,
                        confidence=0.9,
                        evidence="CDX returned no capture rows",
                    ),
                )
            )

        oldest, newest = captures[0], captures[-1]
        return ModuleResult(
            data={"count": len(captures), "captures": captures},
            findings=(
                make_finding(
                    self.name,
                    f"Wayback: {len(captures)} archived capture(s)",
                    {
                        "count": len(captures),
                        "oldest": oldest["timestamp"],
                        "newest": newest["timestamp"],
                    },
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"{oldest['timestamp']} .. {newest['timestamp']}",
                ),
            ),
        )


def _captures(rows: Any) -> list[dict[str, str]]:
    """Normalize a CDX response (header row + data rows) into dicts."""
    if not isinstance(rows, list) or not rows:
        return []
    header: list[str] = []
    body = rows
    if isinstance(rows[0], list):
        header = [str(column) for column in rows[0]]
        body = rows[1:]
    captures: list[dict[str, str]] = []
    for index, row in enumerate(body):
        if isinstance(row, dict):
            captures.append({str(k): str(v) for k, v in row.items()})
        elif isinstance(row, list):
            captures.append(
                {
                    header[i] if i < len(header) else str(index): str(value)
                    for i, value in enumerate(row)
                }
            )
    return captures


PLUGIN = WaybackPlugin
