"""HTTP presence and security-header probes for a domain (Phase 8, S8.5).

Probes ``http://`` and ``https://`` for the apex, records redirect behavior,
checks reachability of ``robots.txt``/``sitemap.xml``, and reports pass-fail
security-header findings (HSTS/CSP/XFO/referrer/permissions) that feed the
risk engine.  Raw website profiling (title, tech, cookies) is owned by
Phase 10.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.http_client import HttpResponse
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

_SECURITY_HEADERS: dict[str, Severity] = {
    "strict-transport-security": Severity.MEDIUM,
    "content-security-policy": Severity.MEDIUM,
    "x-frame-options": Severity.LOW,
    "referrer-policy": Severity.LOW,
    "permissions-policy": Severity.LOW,
}


def _header_map(response: HttpResponse | None) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in (response.headers if response else {}).items()
    }


class HttpProbeModule(BaseModule):
    """HTTP/HTTPS availability, redirects, robots/sitemap, pass-fail headers."""

    name = "http"
    target_types = (TargetType.DOMAIN,)
    description = "HTTP/HTTPS status, redirects, robots/sitemap, security headers"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        if ctx.http is None:
            raise RuntimeError("http module requires ctx.http")

        https = await self._try_fetch(ctx, f"https://{target}/")
        http = await self._try_fetch(ctx, f"http://{target}/")
        robots = await self._try_fetch(ctx, f"https://{target}/robots.txt")
        sitemap = await self._try_fetch(ctx, f"https://{target}/sitemap.xml")

        findings: list[Any] = []
        data: dict[str, Any] = {"target": target}
        if https is not None:
            data["https"] = {
                "status": https.status,
                "url": https.url,
                "redirects": https.redirects,
            }
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: https responds",
                    {
                        "status": https.status,
                        "url": https.url,
                        "redirects": https.redirects,
                    },
                    severity=Severity.INFO if https.status < 400 else Severity.LOW,
                    confidence=0.9,
                    evidence=f"HTTP {https.status} at {https.url}",
                )
            )
            if https.status in (301, 302, 303, 307, 308) or https.redirects:
                findings.append(
                    make_finding(
                        self.name,
                        "HTTP: redirect chain",
                        {
                            "redirects": https.redirects,
                            "final_url": https.url,
                            "status": https.status,
                        },
                        severity=Severity.LOW,
                        confidence=0.9,
                        evidence=f"{https.status} -> {https.url}",
                    )
                )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: https unreachable",
                    {"target": target},
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="https probe failed",
                )
            )

        if http is not None:
            data["http"] = {
                "status": http.status,
                "url": http.url,
                "redirects": http.redirects,
            }
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: http responds",
                    {
                        "status": http.status,
                        "url": http.url,
                        "redirects": http.redirects,
                    },
                    severity=Severity.INFO if http.status < 400 else Severity.LOW,
                    confidence=0.9,
                    evidence=f"HTTP {http.status} at {http.url}",
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "HTTP: http unreachable",
                    {"target": target},
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="http probe failed",
                )
            )

        for label, response in (("robots.txt", robots), ("sitemap.xml", sitemap)):
            if response is None:
                findings.append(
                    make_finding(
                        self.name,
                        f"HTTP: {label} unreachable",
                        {"label": label},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=f"{label} fetch failed",
                    )
                )
            elif response.status < 400:
                findings.append(
                    make_finding(
                        self.name,
                        f"HTTP: {label} present",
                        {"label": label, "status": response.status},
                        severity=Severity.INFO,
                        confidence=0.9,
                        evidence=f"HTTP {response.status}",
                    )
                )
            else:
                findings.append(
                    make_finding(
                        self.name,
                        f"HTTP: no {label}",
                        {"label": label, "status": response.status},
                        severity=Severity.LOW,
                        confidence=0.9,
                        evidence=f"HTTP {response.status}",
                    )
                )

        headers = _header_map(https)
        for header, absent_severity in _SECURITY_HEADERS.items():
            value = headers.get(header)
            if value:
                findings.append(
                    make_finding(
                        self.name,
                        f"HTTP: {header} present",
                        {"header": header, "value": value},
                        severity=Severity.INFO,
                        confidence=0.9,
                        evidence=value,
                    )
                )
            else:
                findings.append(
                    make_finding(
                        self.name,
                        f"HTTP: missing {header}",
                        {"header": header},
                        severity=absent_severity,
                        confidence=0.8,
                        evidence=f"{header} not sent over https",
                    )
                )
        return ModuleResult(data=data, findings=findings)

    async def _try_fetch(self, ctx: ModuleContext, url: str) -> HttpResponse | None:
        if ctx.http is None:
            return None
        try:
            return await ctx.http.fetch(url)
        except Exception:
            return None
