"""Conservative IP reputation checks (Phase 9, S9.3).

Only authorized/conservative sources are used: a Spamhaus ZEN DNSBL probe
(127.0.0.2-11 delisting codes resolved over DNS-over-HTTPS) plus an optional
AbuseIPDB API check that only runs when an ``abuseipdb`` API key is
configured.  IPv6 addresses are reported as out-of-scope for the IPv4-only
DNSBL rather than failing; an unavailable source degrades to a LOW finding.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.ip._dns import dnsbl_name, query_answers

ZEN_RECORDS: dict[str, tuple[str, str]] = {
    "127.0.0.2": ("SBL", "spam source"),
    "127.0.0.3": ("SBL+CSS", "spam source with botnet/exploit involvement"),
    "127.0.0.4": ("XBL", "criminal/botnet infrastructure"),
    "127.0.0.5": ("SBL+XBL", "spam source and botnet infrastructure"),
    "127.0.0.6": ("CSS", "bad-configured host"),
    "127.0.0.7": ("CSS", "bad-configured host"),
    "127.0.0.8": ("CSS", "bad-configured host"),
    "127.0.0.9": ("PBL", "reserved or dynamic space"),
    "127.0.0.10": ("PBL", "reserved or dynamic space"),
    "127.0.0.11": ("PBL", "reserved or dynamic space"),
}


class ReputationModule(BaseModule):
    """Spamhaus ZEN DNSBL probe plus optional AbuseIPDB enrichment."""

    name = "reputation"
    target_types = (TargetType.IP,)
    description = "IP reputation via Spamhaus ZEN DNSBL and optional AbuseIPDB"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        endpoint = str(
            ctx.config.get(
                "reputation.endpoint", "https://cloudflare-dns.com/dns-query"
            )
        )
        zone = str(ctx.config.get("reputation.dnsbl_zone", "zen.spamhaus.org"))

        host = dnsbl_name(target, zone)
        dnsbl: dict[str, Any] = {"zone": zone, "listed": False, "records": []}
        findings: list[Any] = []
        if host is None:
            dnsbl.update(state="skipped")
            findings.append(
                make_finding(
                    self.name,
                    "Reputation: IPv6 out of scope for DNSBL",
                    {"zone": zone, "reason": "Spamhaus ZEN is IPv4-only"},
                    severity=Severity.INFO,
                    confidence=1.0,
                    evidence="IPv6 target",
                )
            )
        else:
            try:
                answers = await query_answers(ctx, endpoint, host, "A")
                records = sorted(
                    {
                        str(answer.get("data", ""))
                        for answer in answers
                        if answer.get("data")
                    }
                )
                listed = [record for record in records if record in ZEN_RECORDS]
                dnsbl = {
                    "zone": zone,
                    "listed": bool(listed),
                    "records": records,
                    "state": "ok",
                }
                if listed:
                    details = [
                        {
                            "address": record,
                            "code": ZEN_RECORDS[record][0],
                            "label": ZEN_RECORDS[record][1],
                        }
                        for record in listed
                    ]
                    findings.append(
                        make_finding(
                            self.name,
                            "Reputation: DNSBL listing",
                            {"zone": zone, "records": details},
                            severity=Severity.HIGH,
                            confidence=0.95,
                            evidence=f"{len(listed)} listing(s) in {zone}",
                        )
                    )
                else:
                    findings.append(
                        make_finding(
                            self.name,
                            "Reputation: DNSBL clean",
                            {"zone": zone},
                            severity=Severity.INFO,
                            confidence=0.9,
                            evidence=f"no listing in {zone}",
                        )
                    )
            except Exception as exc:
                dnsbl = {
                    "zone": zone,
                    "listed": False,
                    "records": [],
                    "state": "unavailable",
                }
                findings.append(
                    make_finding(
                        self.name,
                        "Reputation: DNSBL check unavailable",
                        {"zone": zone},
                        severity=Severity.LOW,
                        confidence=0.7,
                        evidence=str(exc),
                    )
                )

        abuse = await self._abuseipdb(ctx, target)
        state = abuse["state"]
        if state == "ok" and isinstance(abuse.get("data"), dict):
            entry = abuse["data"]
            score = int(entry.get("abuseConfidenceScore") or 0)
            whitelisted = bool(entry.get("isWhitelisted"))
            if not whitelisted and score > 0:
                findings.append(
                    make_finding(
                        self.name,
                        "Reputation: AbuseIPDB abusive",
                        {
                            "score": score,
                            "country": entry.get("countryCode"),
                            "usage": entry.get("usageType"),
                        },
                        severity=Severity.HIGH,
                        confidence=0.9,
                        evidence=f"abuse confidence {score}%",
                    )
                )
            elif whitelisted:
                findings.append(
                    make_finding(
                        self.name,
                        "Reputation: AbuseIPDB whitelisted",
                        {"score": score, "country": entry.get("countryCode")},
                        severity=Severity.INFO,
                        confidence=0.9,
                        evidence=f"abuse confidence {score}%",
                    )
                )
            else:
                findings.append(
                    make_finding(
                        self.name,
                        "Reputation: AbuseIPDB clean",
                        {"score": score, "country": entry.get("countryCode")},
                        severity=Severity.INFO,
                        confidence=0.85,
                        evidence=f"abuse confidence {score}%",
                    )
                )
        elif state == "unavailable":
            findings.append(
                make_finding(
                    self.name,
                    "Reputation: AbuseIPDB check unavailable",
                    {"error": abuse.get("error")},
                    severity=Severity.LOW,
                    confidence=0.7,
                    evidence="AbuseIPDB probe failed",
                )
            )

        degraded = (
            dnsbl.get("state") == "unavailable" or abuse["state"] == "unavailable"
        )
        data: dict[str, Any] = {
            "target": target,
            "state": "degraded" if degraded else "ok",
            "source": endpoint,
            "dnsbl": dnsbl,
            "abuseipdb": abuse,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": endpoint})

    async def _abuseipdb(self, ctx: ModuleContext, target: str) -> dict[str, Any]:
        """Optional AbuseIPDB check; only runs when an ``abuseipdb`` key exists."""
        key = ctx.api_key("abuseipdb")
        if not key:
            return {"state": "no_key"}
        if ctx.http is None:
            return {"state": "unavailable", "error": "module requires ctx.http"}
        endpoint = str(
            ctx.config.get(
                "reputation.abuseipdb_endpoint",
                "https://api.abuseipdb.com/api/v2/check",
            )
        )
        try:
            payload = await ctx.http.get_json(
                endpoint,
                params={"ipAddress": target, "maxAgeInDays": 90},
                headers={"Key": key, "Accept": "application/json"},
            )
        except Exception as exc:
            return {"state": "unavailable", "error": str(exc)}
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return {"state": "unavailable", "error": "non-JSON response body"}
        return {"state": "ok", "data": payload["data"], "endpoint": endpoint}
