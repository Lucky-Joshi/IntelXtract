"""HTTP method / page-title probes (Phase 10, S10.5).

Sends OPTIONS and HEAD probes to the target (non-raising) to learn the
allowed methods, then a GET for the page title and content type.  An
enabled ``TRACE`` method is reported as a MEDIUM finding; missing pages and
unreachable hosts degrade to LOW findings instead of failing the scan.
"""

from __future__ import annotations

import re
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

_TITLE_RE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.I | re.S)


class HttpMethodsModule(BaseModule):
    """OPTIONS/HEAD probes plus page title and content type."""

    name = "http_methods"
    target_types = (TargetType.URL,)
    description = "Allowed HTTP methods, page title, and content type"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        max_body = int(ctx.config.get("website.max_body_size", 262_144))
        try:
            options = await self.http_fetch(
                ctx, target, method="OPTIONS", allow_redirects=False
            )
            head = await self.http_fetch(
                ctx, target, method="HEAD", allow_redirects=True
            )
            body = await self.http_fetch(ctx, target)
        except Exception as exc:
            return ModuleResult(
                data={"target": target, "state": "unavailable"},
                findings=[
                    make_finding(
                        self.name,
                        "HTTP: probe unavailable",
                        {"target": target},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=str(exc),
                    )
                ],
                meta={"source": target},
            )

        allowed = _allowed_methods(options)
        html = body.body[:max_body].decode("utf-8", errors="replace")
        title_match = _TITLE_RE.search(html)
        title = title_match.group(1).strip() if title_match else None
        content_type = str(
            {key.lower(): str(value) for key, value in body.headers.items()}.get(
                "content-type", ""
            )
        )

        findings: list[Any] = []
        if allowed:
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: allowed methods",
                    {"methods": allowed},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=", ".join(allowed),
                )
            )
            if "TRACE" in allowed:
                findings.append(
                    make_finding(
                        self.name,
                        "HTTP: TRACE enabled",
                        {"methods": allowed},
                        severity=Severity.MEDIUM,
                        confidence=0.9,
                        evidence="TRACE is advertised by the server",
                    )
                )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: OPTIONS restricted",
                    {"status": options.status},
                    severity=Severity.INFO,
                    confidence=0.8,
                    evidence=f"OPTIONS returned HTTP {options.status} with no Allow",
                )
            )

        if title:
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: page title",
                    {"title": title},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=title,
                )
            )
        findings.append(
            make_finding(
                self.name,
                "HTTP: page profile",
                {
                    "status": body.status,
                    "content_type": content_type or None,
                    "redirects": body.redirects,
                },
                severity=Severity.INFO,
                confidence=0.95,
                evidence=f"HTTP {body.status}, {content_type or 'no content-type'}",
            )
        )

        data: dict[str, Any] = {
            "target": target,
            "state": "ok",
            "status": body.status,
            "methods": allowed,
            "title": title,
            "content_type": content_type or None,
            "head_status": head.status,
            "body_url": body.url,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": target})


def _allowed_methods(options: Any) -> list[str]:
    """Normalize the Allow header from an OPTIONS response."""
    if options.status >= 400:
        return []
    allow = {key.lower(): str(value) for key, value in options.headers.items()}.get(
        "allow"
    )
    if not allow:
        return []
    return [method.strip().upper() for method in allow.split(",") if method.strip()]
