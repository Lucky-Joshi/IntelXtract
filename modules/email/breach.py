"""S11.4 — key-gated breach check (HIBP) with graceful skip.

Runs only when ``api_keys.hibp`` is configured; the engine's planner emits a
``skipped`` run otherwise, so a missing key never fails a scan.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from core.constants import APP_NAME, Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

DEFAULT_BREACH_ENDPOINT = "https://haveibeenpwned.com/api/v3/breachedaccount/"


class BreachModule(BaseModule):
    """Look up an address against HIBP's breach API (requires ``hibp`` key)."""

    name = "breach"
    target_types = (TargetType.EMAIL,)
    requires_keys = ("hibp",)
    description = "HIBP breach exposure (key-gated)"
    timeout = 20.0

    def validate(self, target: str) -> bool:
        return "@" in target

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        email = target.strip().lower()
        endpoint = str(ctx.config.get("email.breach_endpoint", DEFAULT_BREACH_ENDPOINT))
        api_key = str(ctx.config.get("api_keys.hibp", "") or "")
        findings: list[Any] = []
        data: dict[str, Any] = {
            "target": email,
            "state": "ok",
            "breaches": [],
            "count": 0,
        }

        url = f"{endpoint}{quote(email, safe='')}?truncateResponse=false"
        try:
            response = await self.http_fetch(
                ctx,
                url,
                headers={
                    "hibp-api-key": api_key,
                    "user-agent": APP_NAME,
                },
            )
        except Exception:
            data["state"] = "unavailable"
            findings.append(
                make_finding(
                    self.name,
                    "Breach: check unavailable",
                    {"target": email},
                    severity=Severity.LOW,
                    confidence=0.3,
                    evidence="HIBP request failed",
                )
            )
            return ModuleResult(data=data, findings=findings)

        if response.status == 404:
            findings.append(
                make_finding(
                    self.name,
                    "Breach: no known breaches",
                    {"target": email},
                    severity=Severity.INFO,
                    confidence=0.7,
                    evidence="HIBP returned 404 (not found)",
                )
            )
            return ModuleResult(data=data, findings=findings)

        if response.status == 401:
            data["state"] = "unauthorized"
            findings.append(
                make_finding(
                    self.name,
                    "Breach: API key rejected",
                    {"target": email, "status": 401},
                    severity=Severity.MEDIUM,
                    confidence=0.9,
                    evidence="HIBP rejected the configured api key",
                )
            )
            return ModuleResult(data=data, findings=findings)

        if response.status != 200:
            data["state"] = "degraded"
            findings.append(
                make_finding(
                    self.name,
                    "Breach: unexpected API response",
                    {"target": email, "status": response.status},
                    severity=Severity.LOW,
                    confidence=0.5,
                    evidence=f"HIBP returned HTTP {response.status}",
                )
            )
            return ModuleResult(data=data, findings=findings)

        breaches = self._parse(response.body)
        data["breaches"] = breaches
        data["count"] = len(breaches)
        if breaches:
            findings.append(
                make_finding(
                    self.name,
                    "Breach: address exposed in known breach(es)",
                    {"target": email, "breaches": breaches},
                    severity=Severity.HIGH,
                    confidence=0.9,
                    evidence=f"{len(breaches)} breach(es): {', '.join(breaches[:5])}",
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "Breach: no known breaches",
                    {"target": email},
                    severity=Severity.INFO,
                    confidence=0.7,
                    evidence="HIBP returned empty result",
                )
            )
        return ModuleResult(data=data, findings=findings)

    @staticmethod
    def _parse(body: bytes) -> list[str]:
        import json

        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError:
            return []
        if not isinstance(payload, list):
            return []
        names = [
            item.get("Name")
            for item in payload
            if isinstance(item, dict) and item.get("Name")
        ]
        return [str(name) for name in names]
