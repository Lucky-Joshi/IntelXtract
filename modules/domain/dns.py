"""DoH-based DNS record collection for a domain (Phase 8, S8.2).

Queries ``dns.endpoint`` (a DNS-over-HTTPS JSON service) for A/AAAA/CNAME/NS/
MX/TXT records plus SPF and DMARC policy TXT records and a bounded DKIM
selector probe.  No raw UDP/TCP DNS sockets are used, so the shared HTTP
client keeps everything testable and retryable.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

DNS_TYPES: dict[str, str] = {
    "A": "A",
    "AAAA": "AAAA",
    "CNAME": "CNAME",
    "NS": "NS",
    "MX": "MX",
    "TXT": "TXT",
}


class DnsModule(BaseModule):
    """DNS records, SPF/DMARC policy, and a bounded DKIM selector probe."""

    name = "dns"
    target_types = (TargetType.DOMAIN,)
    description = "DNS records via DoH (A/AAAA/CNAME/NS/MX/TXT, SPF, DMARC, DKIM)"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        endpoint = str(
            ctx.config.get("dns.endpoint", "https://cloudflare-dns.com/dns-query")
        )
        selectors = list(ctx.config.get("dns.selectors", []))

        records: dict[str, list[str]] = {}
        queries: list[str] = []
        for dns_type in DNS_TYPES:
            answers = await self._query(ctx, endpoint, target, dns_type)
            queries.append(dns_type)
            values = [str(answer.get("data", "")) for answer in answers]
            records[dns_type] = [value for value in values if value]

        spf = "".join(records.get("TXT", []))
        dmarc_values = [
            str(answer.get("data", ""))
            for answer in await self._query(ctx, endpoint, f"_dmarc.{target}", "TXT")
        ]
        dmarc = next((v for v in dmarc_values if "v=DMARC1" in v), None)

        dkim_found: dict[str, str] = {}
        for selector in selectors:
            if not isinstance(selector, str) or not selector:
                continue
            values = [
                str(answer.get("data", ""))
                for answer in await self._query(
                    ctx, endpoint, f"{selector}._domainkey.{target}", "TXT"
                )
            ]
            if values:
                dkim_found[selector] = " ".join(values)

        return self._build(target, endpoint, records, spf, dmarc, dkim_found)

    async def _query(
        self, ctx: ModuleContext, endpoint: str, name: str, dns_type: str
    ) -> list[dict[str, Any]]:
        payload = await self.http_get_json(
            ctx,
            endpoint,
            params={"name": name, "type": dns_type},
            headers={"Accept": "application/dns-json"},
        )
        if not isinstance(payload, dict):
            return []
        answers = payload.get("Answer")
        if not isinstance(answers, list):
            return []
        return [answer for answer in answers if isinstance(answer, dict)]

    def _build(
        self,
        target: str,
        endpoint: str,
        records: dict[str, list[str]],
        spf: str,
        dmarc: str | None,
        dkim_found: dict[str, str],
    ) -> ModuleResult:
        findings: list[Any] = []
        for dns_type in DNS_TYPES:
            values = records.get(dns_type, [])
            if dns_type == "CNAME" and not values:
                continue
            findings.append(
                make_finding(
                    self.name,
                    f"DNS: {dns_type} records",
                    {"type": dns_type, "records": values},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"{len(values)} record(s)",
                )
            )

        if "v=spf1" in spf:
            findings.append(
                make_finding(
                    self.name,
                    "DNS: SPF record",
                    {"record": spf.strip()},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=spf.strip(),
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "DNS: no SPF record",
                    {"record": None},
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="no v=spf1 TXT record found",
                )
            )

        if dmarc:
            findings.append(
                make_finding(
                    self.name,
                    "DNS: DMARC record",
                    {"record": dmarc},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=dmarc,
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "DNS: no DMARC record",
                    {"record": None},
                    severity=Severity.LOW,
                    confidence=0.7,
                    evidence="no v=DMARC1 TXT record found",
                )
            )

        for selector, value in dkim_found.items():
            findings.append(
                make_finding(
                    self.name,
                    f"DNS: DKIM selector '{selector}'",
                    {"selector": selector, "record": value},
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=value,
                )
            )

        data: dict[str, Any] = {
            "target": target,
            "source": endpoint,
            "records": records,
            "spf": spf.strip() or None,
            "dmarc": dmarc,
            "dkim": dkim_found,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": endpoint})
