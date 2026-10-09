"""Favicon fetch + fingerprint (Phase 10, S10.3).

Fetches ``<origin><website.favicon_path>`` (default ``/favicon.ico``) and
computes a stable 32-bit fingerprint as FNV-1a over the canonical Shodan-style
preimage: ``base64(md5(icon_bytes))``.  The result can be correlated across
sites sharing an icon without relying on any third-party fingerprint API.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.website._util import absolute

FNV_OFFSET = 2166136261
FNV_PRIME = 16777619


def _fnv1a_32(text: str) -> int:
    """32-bit FNV-1a hash over ``text``'s UTF-8 bytes."""
    value = FNV_OFFSET
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFF
    return value


def favicon_hash(body: bytes) -> int:
    """Shodan-style fingerprint: FNV-1a over base64(md5(body))."""
    digest = base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode(
        "ascii"
    )
    return _fnv1a_32(digest)


class FaviconModule(BaseModule):
    """Fetch and fingerprint a site's favicon for cross-site correlation."""

    name = "favicon"
    target_types = (TargetType.URL,)
    description = "Favicon fingerprint (FNV-1a over base64 md5)"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        favicon_path = str(ctx.config.get("website.favicon_path", "/favicon.ico"))
        url = absolute(target, favicon_path)
        try:
            response = await self.http_fetch(ctx, url)
        except Exception as exc:
            return ModuleResult(
                data={"target": target, "state": "unavailable", "url": url},
                findings=[
                    make_finding(
                        self.name,
                        "Favicon: lookup unavailable",
                        {"target": target},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=str(exc),
                    )
                ],
                meta={"source": url},
            )

        if response.status in (404, 403):
            return ModuleResult(
                data={
                    "target": target,
                    "state": "missing",
                    "url": url,
                    "status": response.status,
                },
                findings=[
                    make_finding(
                        self.name,
                        "Favicon: not found",
                        {"path": favicon_path},
                        severity=Severity.LOW,
                        confidence=0.9,
                        evidence=f"HTTP {response.status} for {favicon_path}",
                    )
                ],
                meta={"source": url},
            )

        fingerprint = favicon_hash(response.body)
        content_type = str(
            {key.lower(): str(value) for key, value in response.headers.items()}.get(
                "content-type", "application/octet-stream"
            )
        )
        data: dict[str, Any] = {
            "target": target,
            "state": "ok",
            "url": url,
            "status": response.status,
            "size": len(response.body),
            "content_type": content_type,
            "hash": fingerprint,
        }
        return ModuleResult(
            data=data,
            findings=[
                make_finding(
                    self.name,
                    "Favicon: fingerprint",
                    {"hash": fingerprint, "size": data["size"]},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=str(fingerprint),
                )
            ],
            meta={"source": url},
        )
