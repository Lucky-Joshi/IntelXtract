"""VirusTotal domain report plugin — living reference for the Plugin SDK.

Key-gated example: declares ``required_keys = ("virustotal",)`` so the engine
planner skips it unless an ``api_keys.virustotal`` value is configured. When it
does run it turns VirusTotal's ``last_analysis_stats`` into a severity-graded
finding. See ``docs/plugin_sdk.md``.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from core.plugin_loader import PluginBase

VT_URL = "https://www.virustotal.com/api/v3/domains/{target}"


class VirusTotalPlugin(PluginBase):
    """Report VirusTotal reputation detections for a domain."""

    name = "virustotal"
    version = "1.0.0"
    author = "IntelXtract"
    description = "VirusTotal domain reputation report."
    target_types = (TargetType.DOMAIN,)
    requires_keys = ("virustotal",)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        api_key = ctx.api_key("virustotal")
        if not api_key:
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "VirusTotal: not configured",
                        {"target": target},
                        severity=Severity.INFO,
                        confidence=0.2,
                        evidence="missing api key 'virustotal'",
                    ),
                )
            )
        try:
            payload = await ctx.http.get_json(
                VT_URL.format(target=target),
                headers={"x-apikey": api_key},
            )
        except Exception as exc:
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "VirusTotal: lookup unavailable",
                        {"target": target, "error": str(exc)},
                        severity=Severity.INFO,
                        confidence=0.3,
                        evidence=f"VirusTotal request failed: {exc}",
                    ),
                )
            )
        attributes = ((payload or {}).get("data") or {}).get("attributes") or {}
        stats = attributes.get("last_analysis_stats") or {}
        malicious = _int(stats.get("malicious"))
        suspicious = _int(stats.get("suspicious"))
        total = sum(_int(value) for value in stats.values())
        severity = (
            Severity.CRITICAL
            if malicious >= 5
            else (
                Severity.HIGH
                if malicious >= 1
                else Severity.MEDIUM if suspicious else Severity.INFO
            )
        )
        return ModuleResult(
            data={"stats": stats, "total_engines": total},
            findings=(
                make_finding(
                    self.name,
                    f"VirusTotal: {malicious} malicious / "
                    f"{suspicious} suspicious detection(s)",
                    {
                        "malicious": malicious,
                        "suspicious": suspicious,
                        "harmless": _int(stats.get("harmless")),
                        "undetected": _int(stats.get("undetected")),
                    },
                    severity=severity,
                    confidence=0.8,
                    evidence=f"{malicious} malicious of {total} engine(s)",
                ),
            ),
        )


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


PLUGIN = VirusTotalPlugin
