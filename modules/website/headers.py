"""HTTP response headers, server disclosure, cookies (Phase 10, S10.1).

Fetches the target and profiles the final response: server/powered-by
disclosure, compression, security headers, and cookie flags
(Secure/HttpOnly/SameSite).  Insecure cookies and missing protections are
emitted with severity so the risk engine can weigh them later.
"""

from __future__ import annotations

import re
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.http_client import HttpResponse
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
)

_COOKIE_ATTRS = re.compile(r";\s*([A-Za-z-]+)(?:=([^;\s]*))?")


class HeadersModule(BaseModule):
    """Full response headers, server disclosure, compression, and cookies."""

    name = "headers"
    target_types = (TargetType.URL,)
    description = "HTTP response headers, cookie flags, and disclosures"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        try:
            response = await self.http_fetch(ctx, target)
        except Exception as exc:
            return ModuleResult(
                data={"target": target, "state": "unavailable"},
                findings=[
                    make_finding(
                        self.name,
                        "Headers: lookup unavailable",
                        {"target": target},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=str(exc),
                    )
                ],
                meta={"source": target},
            )
        return self._build(target, response)

    def _build(self, target: str, response: HttpResponse) -> ModuleResult:
        headers = {key.lower(): str(value) for key, value in response.headers.items()}
        server = headers.get("server")
        powered_by = headers.get("x-powered-by")
        encoding = headers.get("content-encoding")
        content_type = headers.get("content-type")

        security: dict[str, bool] = {}
        for name in SECURITY_HEADERS:
            security[name] = name in headers

        cookies = _parse_cookies(headers.get("set-cookie", ""))

        findings: list[Any] = []
        if server or powered_by:
            findings.append(
                make_finding(
                    self.name,
                    "Headers: server disclosure",
                    {"server": server, "x_powered_by": powered_by},
                    severity=Severity.MEDIUM,
                    confidence=0.85,
                    evidence=(server or powered_by or ""),
                )
            )

        for name, present in security.items():
            if present:
                findings.append(
                    make_finding(
                        self.name,
                        f"Headers: {name} present",
                        {"header": name},
                        severity=Severity.INFO,
                        confidence=0.95,
                        evidence=headers[name],
                    )
                )
            else:
                findings.append(
                    make_finding(
                        self.name,
                        f"Headers: {name} missing",
                        {"header": name},
                        severity=Severity.LOW,
                        confidence=0.9,
                        evidence=f"{name} header absent",
                    )
                )

        if encoding:
            findings.append(
                make_finding(
                    self.name,
                    "Headers: response compression",
                    {"encoding": encoding},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=encoding,
                )
            )

        for cookie in cookies:
            flags = {flag.lower() for flag in cookie["flags"]}
            missing = [
                expected
                for expected in ("Secure", "HttpOnly", "SameSite")
                if expected.lower() not in flags
            ]
            if not missing:
                continue
            findings.append(
                make_finding(
                    self.name,
                    "Headers: insecure cookie",
                    {"cookie": cookie["name"], "missing": missing},
                    severity=Severity.MEDIUM if "Secure" in missing else Severity.LOW,
                    confidence=0.85,
                    evidence=f"{cookie['name']} lacks {'/'.join(missing)}",
                )
            )

        findings.append(
            make_finding(
                self.name,
                "Headers: response profile",
                {
                    "status": response.status,
                    "content_type": content_type,
                    "compression": encoding,
                    "redirects": response.redirects,
                    "server": server,
                },
                severity=Severity.INFO,
                confidence=0.95,
                evidence=f"HTTP {response.status} via {response.url}",
            )
        )

        data: dict[str, Any] = {
            "target": target,
            "state": "ok",
            "url": response.url,
            "status": response.status,
            "redirects": response.redirects,
            "headers": dict(response.headers),
            "server": server,
            "x_powered_by": powered_by,
            "compression": encoding,
            "content_type": content_type,
            "security": security,
            "cookies": cookies,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": response.url})


def _parse_cookies(raw: str) -> list[dict[str, Any]]:
    """Split a ``Set-Cookie`` header value into ``[{name, value, flags}]``.

    Cookie records are comma-delimited (an attribute value containing a comma,
    e.g. ``Expires``, is handled by tracking quoted strings).  Attributes are
    normalized to lowercase names so callers can check for ``secure``,
    ``httponly`` and ``samesite``.
    """
    parsed: list[dict[str, Any]] = []
    for record in _split_cookie_header(raw):
        head, _, rest = record.partition(";")
        name, _, value = head.partition("=")
        flags = [
            attr.group(1).lower()
            for attr in _COOKIE_ATTRS.finditer(f";{rest}")
            if attr.group(1)
        ]
        parsed.append({"name": name.strip(), "value": value.strip(), "flags": flags})
    return parsed


def _split_cookie_header(raw: str) -> list[str]:
    """Split a ``Set-Cookie`` header into individual cookie records."""
    records: list[str] = []
    current: list[str] = []
    in_quotes = False
    for char in raw:
        if char == '"':
            in_quotes = not in_quotes
        if char == "," and not in_quotes:
            records.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        records.append("".join(current))
    return [record.strip() for record in records if record.strip()]
