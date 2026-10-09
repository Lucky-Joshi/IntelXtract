"""IP geolocation via ip-api.org (Phase 9, S9.1).

Fetches coarse location (country/region/city/timezone) plus network facts
(ISP, organization, ASN) from the free, keyless ``ip-api.com`` endpoint.
Successful responses are cached in ``ctx.cache`` against later re-scans of
the same address; a failed or unknown lookup degrades to a LOW finding
instead of failing the scan.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule


class GeoModule(BaseModule):
    """ASN, ISP, and coarse country/region/city for an IP address."""

    name = "geo"
    target_types = (TargetType.IP,)
    description = "IP geolocation and network facts (ip-api.org, cached)"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        endpoint = str(ctx.config.get("geo.endpoint", "http://ip-api.com/json/"))
        ttl = float(ctx.config.get("geo.cache_ttl", 86400.0))
        url = f"{endpoint.rstrip('/')}/{target}"
        cache_key = f"geo:{target}"

        cached = await ctx.cache.get(cache_key)
        if isinstance(cached, dict):
            return self._build(target, url, cached, source="cache")
        if cached is not None:
            return self._unavailable(target, url, "cached lookup had no data")

        try:
            payload = await self.http_get_json(ctx, url)
        except Exception as exc:
            return self._unavailable(target, url, f"request failed: {exc}")
        if not isinstance(payload, dict):
            return self._unavailable(target, url, "non-JSON response body")

        await ctx.cache.set(cache_key, payload, ttl=ttl)
        return self._build(target, url, payload, source="api")

    def _unavailable(self, target: str, url: str, reason: str) -> ModuleResult:
        return ModuleResult(
            data={"target": target, "source": url, "state": "unavailable"},
            findings=[
                make_finding(
                    self.name,
                    "Geo: lookup unavailable",
                    {"target": target, "state": "unavailable"},
                    severity=Severity.LOW,
                    confidence=0.7,
                    evidence=reason,
                )
            ],
            meta={"source": url},
        )

    def _build(
        self, target: str, url: str, payload: dict[str, Any], *, source: str
    ) -> ModuleResult:
        if payload.get("status") != "success":
            return self._unavailable(
                target, url, f"provider status: {payload.get('status')!r}"
            )

        data: dict[str, Any] = {
            "target": target,
            "source": url,
            "state": "ok",
            "data_source": source,
            "query": payload.get("query"),
            "country": payload.get("country"),
            "country_code": payload.get("countryCode"),
            "region": payload.get("region"),
            "city": payload.get("city"),
            "timezone": payload.get("timezone"),
            "latitude": payload.get("lat"),
            "longitude": payload.get("lon"),
            "isp": payload.get("isp"),
            "organization": payload.get("org"),
            "asn": payload.get("as"),
        }

        location_parts = [
            part
            for part in (data["city"], data["region"], data["country"])
            if part is not None
        ]
        findings: list[Any] = [
            make_finding(
                self.name,
                "Geo: IP location",
                {
                    "country": data["country"],
                    "country_code": data["country_code"],
                    "region": data["region"],
                    "city": data["city"],
                },
                severity=Severity.INFO,
                confidence=0.9,
                evidence=", ".join(str(part) for part in location_parts) or "unknown",
            ),
            make_finding(
                self.name,
                "Geo: network",
                {
                    "isp": data["isp"],
                    "organization": data["organization"],
                    "asn": data["asn"],
                },
                severity=Severity.INFO,
                confidence=0.9,
                evidence=str(data["asn"] or data["isp"] or "unknown"),
            ),
        ]
        return ModuleResult(data=data, findings=findings, meta={"source": url})
