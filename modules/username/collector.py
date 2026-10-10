"""Phase 12 registered collector: ``username``.

Fans out the ``sites.json`` pattern list concurrently (per-site paced),
classifies each verdict conservatively, and enriches GitHub public profiles
where available.
"""

from __future__ import annotations

import re
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.username.enrichment import github_profile
from modules.username.sites import load_sites
from modules.username.social import (
    VERDICT_EXISTS,
    VERDICT_MISSING,
    VERDICT_UNKNOWN,
    check_sites,
)

_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,31}$")


class UsernameModule(BaseModule):
    """Probe public profile-enabling sites for a handle's presence."""

    name = "username"
    target_types = (TargetType.USERNAME,)
    description = "Public username presence checks across 30+ sites"
    timeout = 45.0

    def validate(self, target: str) -> bool:
        return bool(_USERNAME_RE.match(target))

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        handle = target.strip().lstrip("@")
        sites = load_sites(ctx.config)
        concurrency = int(ctx.config.get("username.concurrency", 8))
        interval = float(ctx.config.get("username.per_site_interval", 1.0))

        results = await check_sites(
            ctx,
            sites,
            handle,
            concurrency=concurrency,
            per_site_interval=interval,
        )

        by_name = {item["name"]: item for item in results}
        exists = [item for item in results if item["verdict"] == VERDICT_EXISTS]
        missing = [item for item in results if item["verdict"] == VERDICT_MISSING]
        unknown = [item for item in results if item["verdict"] == VERDICT_UNKNOWN]

        findings: list[Any] = []
        for item in sorted(exists, key=lambda entry: entry["name"]):
            findings.append(
                make_finding(
                    self.name,
                    f"Username: exists on {item['name']}",
                    {"url": item["url"], "status": item["status"]},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=item["url"],
                )
            )

        findings.append(
            make_finding(
                self.name,
                "Username: profile summary",
                data={
                    "probed": len(results),
                    "exists": len(exists),
                    "missing": len(missing),
                    "unknown": len(unknown),
                },
                severity=Severity.INFO,
                confidence=0.9,
                evidence=(
                    f"{len(exists)} present, {len(missing)} absent, "
                    f"{len(unknown)} unknown across {len(results)} sites"
                ),
            )
        )

        data: dict[str, Any] = {
            "target": handle,
            "state": "ok",
            "probed": len(results),
            "exists": len(exists),
            "missing": len(missing),
            "unknown": len(unknown),
            "sites": by_name,
        }

        if ctx.config.get("username.enrich_github", True) and "GitHub" in by_name:
            if by_name["GitHub"]["verdict"] == VERDICT_EXISTS:
                profile = await github_profile(ctx, handle)
                if profile:
                    data["enrichment"] = {"github": profile}
                    findings.append(
                        make_finding(
                            self.name,
                            "Username: GitHub profile enrichment",
                            data={
                                "login": profile.get("login"),
                                "name": profile.get("name"),
                                "avatar_url": profile.get("avatar_url"),
                                "html_url": profile.get("html_url"),
                                "bio": profile.get("bio"),
                            },
                            severity=Severity.INFO,
                            confidence=0.9,
                            evidence=profile.get("html_url") or "",
                        )
                    )

        if unknown and not exists:
            data["state"] = "degraded"
            findings.append(
                make_finding(
                    self.name,
                    "Username: all site verdicts unknown",
                    {"probed": len(results), "unknown": len(unknown)},
                    severity=Severity.LOW,
                    confidence=0.5,
                    evidence=(
                        "no site confirmed presence; blocked/ambiguous replies "
                        "reported as unknown"
                    ),
                )
            )

        return ModuleResult(data=data, findings=findings)
