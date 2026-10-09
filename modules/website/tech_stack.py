"""CMS/framework/library detection from headers and HTML (Phase 10, S10.2).

Uses an internal signature rule table (no third-party fingerprint API).  Each
rule fires when any of its header / cookie / HTML patterns match; every hit
maps to an informational finding naming the technology and the evidence that
triggered it.
"""

from __future__ import annotations

import re
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

Rule = dict[str, Any]
_TECH_RULES: tuple[Rule, ...] = (
    {
        "name": "WordPress",
        "header": None,
        "cookie": None,
        "pattern": re.compile(r"wp-content|wp-includes|wordpress", re.I),
        "confidence": 0.9,
    },
    {
        "name": "Drupal",
        "header": "x-drupal-cache",
        "cookie": None,
        "pattern": re.compile(r"drupal", re.I),
        "confidence": 0.9,
    },
    {
        "name": "Joomla",
        "header": "x-content-encoded-by",
        "cookie": None,
        "pattern": re.compile(r"joomla", re.I),
        "confidence": 0.85,
    },
    {
        "name": "nginx",
        "header": "server",
        "cookie": None,
        "pattern": re.compile(r"nginx", re.I),
        "confidence": 0.9,
    },
    {
        "name": "Apache",
        "header": "server",
        "cookie": None,
        "pattern": re.compile(r"apache", re.I),
        "confidence": 0.9,
    },
    {
        "name": "Cloudflare",
        "header": "cf-ray",
        "cookie": None,
        "pattern": re.compile(r"cloudflare", re.I),
        "confidence": 0.85,
    },
    {
        "name": "Django",
        "cookie": "csrftoken",
        "header": None,
        "pattern": re.compile(r"django", re.I),
        "confidence": 0.85,
    },
    {
        "name": "Laravel",
        "cookie": "laravel_session",
        "header": "x-laravel-promo",
        "pattern": re.compile(r"laravel", re.I),
        "confidence": 0.8,
    },
    {
        "name": "Gatsby",
        "header": None,
        "cookie": None,
        "pattern": re.compile(r"___gatsby|__gatsby", re.I),
        "confidence": 0.85,
    },
    {
        "name": "React",
        "header": None,
        "cookie": None,
        "pattern": re.compile(
            r"data-reactroot|data-reactid|id=\"root\"|/static/js/main\.[a-f0-9]+\.chunk",
            re.I,
        ),
        "confidence": 0.8,
    },
    {
        "name": "Vue.js",
        "header": None,
        "cookie": None,
        "pattern": re.compile(r"id=\"app\"|data-v-[a-f0-9]{8}|vue", re.I),
        "confidence": 0.7,
    },
    {
        "name": "Webpack",
        "header": None,
        "cookie": None,
        "pattern": re.compile(r"/static/[A-Za-z0-9._-]+\.[a-f0-9]{8}", re.I),
        "confidence": 0.75,
    },
    {
        "name": "Bootstrap",
        "header": None,
        "cookie": None,
        "pattern": re.compile(r"bootstrap(?:\.min)?\.css|bootstrap\.bundle", re.I),
        "confidence": 0.9,
    },
    {
        "name": "jQuery",
        "header": None,
        "cookie": None,
        "pattern": re.compile(r"jquery(?:\.min)?\.js", re.I),
        "confidence": 0.9,
    },
)


class TechStackModule(BaseModule):
    """CMS/framework/library detection from headers, cookies, and HTML."""

    name = "tech"
    target_types = (TargetType.URL,)
    description = "Tech-stack fingerprinting via headers, cookies, and HTML"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        max_body = int(ctx.config.get("website.max_body_size", 262_144))
        try:
            response = await self.http_fetch(ctx, target)
        except Exception as exc:
            return ModuleResult(
                data={"target": target, "state": "unavailable"},
                findings=[
                    make_finding(
                        self.name,
                        "Tech: fingerprint unavailable",
                        {"target": target},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=str(exc),
                    )
                ],
                meta={"source": target},
            )

        html = response.body[:max_body].decode("utf-8", errors="replace")
        headers = {key.lower(): str(value) for key, value in response.headers.items()}
        cookies = [
            str(cookie.get("name", ""))
            for cookie in _cookies_from_headers(headers.get("set-cookie", ""))
            if cookie.get("name")
        ]
        return self._build(target, headers, html, cookies)

    def _build(
        self,
        target: str,
        headers: dict[str, str],
        html: str,
        cookies: list[str],
    ) -> ModuleResult:
        found: list[dict[str, Any]] = []
        for rule in _TECH_RULES:
            evidence = _match(rule, headers, html, cookies)
            if evidence is not None:
                found.append({"name": rule["name"], "evidence": evidence})

        findings: list[Any] = []
        for hit in found:
            findings.append(
                make_finding(
                    self.name,
                    f"Tech: {hit['name']}",
                    {"technology": hit["name"]},
                    severity=Severity.INFO,
                    confidence=float(hit.get("confidence", 0.8)),
                    evidence=hit["evidence"],
                )
            )

        data: dict[str, Any] = {
            "target": target,
            "state": "ok",
            "technologies": [hit["name"] for hit in found],
            "matched": found,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": target})


def _match(
    rule: Rule, headers: dict[str, str], html: str, cookies: list[str]
) -> str | None:
    """Return a short evidence string when ``rule`` fires, else ``None``."""
    if rule.get("header"):
        value = headers.get(str(rule["header"]))
        if value and rule["pattern"].search(value):
            return f"header {rule['header']}: {value}"
    if rule.get("cookie"):
        if str(rule["cookie"]) in cookies:
            return f"cookie {rule['cookie']} present"
    hit = rule["pattern"].search(html)
    if hit:
        return f"html matched {hit.group(0)!r}"
    return None


def _cookies_from_headers(raw: str) -> list[dict[str, Any]]:
    from modules.website.headers import _parse_cookies

    return _parse_cookies(raw)
