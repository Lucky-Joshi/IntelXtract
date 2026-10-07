"""Passive subdomain discovery via certificate transparency (Phase 8, S8.4).

Queries crt.sh (``subdomain.endpoint``) over the shared HTTP client for
certificates issued to ``%.<domain>`` and lists the matching hostnames.
Only passive public sources are used; active enumeration lands later with
the dedicated subdomain module work.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule


def _extract_names(
    entries: list[dict[str, Any]], domain: str, *, max_results: int
) -> list[str]:
    """Collect hostnames belonging to ``domain`` from crt.sh JSON entries."""
    suffix = f".{domain}"
    names: set[str] = set()
    for entry in entries:
        raw = entry.get("name_value")
        if not isinstance(raw, str):
            raw = entry.get("common_name")
        if not isinstance(raw, str):
            continue
        for line in raw.replace("\r", "\n").splitlines():
            name = line.strip().lower()
            if name.startswith("*."):
                name = name[2:]
            name = name.rstrip(".")
            if not name or name == domain or not name.endswith(suffix):
                continue
            names.add(name)
    return sorted(names)[:max_results]


class SubdomainModule(BaseModule):
    """Certificate-transparency subdomain listing (passive)."""

    name = "subdomain"
    target_types = (TargetType.DOMAIN,)
    description = "passive subdomain discovery via certificate transparency"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        endpoint = str(ctx.config.get("subdomain.endpoint", "https://crt.sh"))
        max_results = int(ctx.config.get("subdomain.max_results", 500))
        payload = await self.http_get_json(
            ctx,
            endpoint,
            params={"q": f"%.{target}", "output": "json"},
        )
        entries = payload if isinstance(payload, list) else []
        subdomains = _extract_names(
            [entry for entry in entries if isinstance(entry, dict)],
            target,
            max_results=max_results,
        )
        return self._build(target, endpoint, subdomains)

    def _build(self, target: str, endpoint: str, subdomains: list[str]) -> ModuleResult:
        count = len(subdomains)
        findings = [
            make_finding(
                self.name,
                "Subdomains: certificate transparency",
                {"domain": target, "count": count, "subdomains": subdomains},
                severity=Severity.INFO,
                confidence=0.8,
                evidence=f"{count} subdomain(s) in certificate transparency",
            )
        ]
        data: dict[str, Any] = {
            "target": target,
            "source": endpoint,
            "count": count,
            "subdomains": subdomains,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": endpoint})
