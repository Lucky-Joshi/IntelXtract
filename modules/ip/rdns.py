"""Reverse DNS and forward-confirmed lookup for an IP (Phase 9, S9.2).

PTR records are resolved over DNS-over-HTTPS (``rdns.endpoint``) so the
shared HTTP client keeps everything testable and no raw sockets are used.
Each returned hostname is then re-resolved (A/AAAA) and compared against the
target address to confirm the record (FCrDNS).  Offline or empty lookups
degrade to LOW findings rather than failing the scan.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule
from modules.ip._dns import query_answers, reverse_name

FWD_TYPES = ("A", "AAAA")


class RdnsModule(BaseModule):
    """Reverse DNS (PTR) with forward-confirmed resolution."""

    name = "rdns"
    target_types = (TargetType.IP,)
    description = "Reverse DNS via DoH PTR plus forward-confirmed lookup"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        endpoint = str(
            ctx.config.get("rdns.endpoint", "https://cloudflare-dns.com/dns-query")
        )
        try:
            address = ipaddress.ip_address(target)
        except ValueError:
            return self._unavailable(
                target, endpoint, f"not a valid IP address: {target!r}"
            )

        try:
            ptr_answers = await query_answers(
                ctx, endpoint, reverse_name(target), "PTR"
            )
        except Exception as exc:
            return self._unavailable(target, endpoint, f"PTR lookup failed: {exc}")

        hostnames = sorted(
            {
                str(answer.get("data", "")).rstrip(".")
                for answer in ptr_answers
                if answer.get("data")
            }
        )
        if not hostnames:
            return ModuleResult(
                data={
                    "target": target,
                    "state": "no_record",
                    "source": endpoint,
                    "reverse": [],
                    "confirmed": [],
                },
                findings=[
                    make_finding(
                        self.name,
                        "RDNS: no PTR record",
                        {"target": target},
                        severity=Severity.LOW,
                        confidence=0.9,
                        evidence="no PTR answer returned",
                    )
                ],
                meta={"source": endpoint},
            )

        confirmed = [
            hostname
            for hostname in hostnames
            if await self._forward_confirms(ctx, endpoint, hostname, address)
        ]

        findings: list[Any] = [
            make_finding(
                self.name,
                "RDNS: PTR record",
                {"records": hostnames},
                severity=Severity.INFO,
                confidence=0.9,
                evidence=", ".join(hostnames),
            )
        ]
        if confirmed:
            findings.append(
                make_finding(
                    self.name,
                    "RDNS: forward-confirmed",
                    {"hostname": confirmed[0], "matches": confirmed},
                    severity=Severity.INFO,
                    confidence=0.95,
                    evidence=confirmed[0],
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "RDNS: forward-confirmation failed",
                    {
                        "records": hostnames,
                        "reason": "no A/AAAA record matched the target",
                    },
                    severity=Severity.LOW,
                    confidence=0.8,
                    evidence="FCrDNS mismatch",
                )
            )

        data: dict[str, Any] = {
            "target": target,
            "state": "ok",
            "source": endpoint,
            "reverse": hostnames,
            "confirmed": confirmed,
        }
        return ModuleResult(data=data, findings=findings, meta={"source": endpoint})

    async def _forward_confirms(
        self,
        ctx: ModuleContext,
        endpoint: str,
        hostname: str,
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> bool:
        try:
            for rtype in FWD_TYPES:
                for answer in await query_answers(ctx, endpoint, hostname, rtype):
                    try:
                        if ipaddress.ip_address(str(answer.get("data", ""))) == address:
                            return True
                    except ValueError:
                        continue
        except Exception:
            return False
        return False

    def _unavailable(self, target: str, source: str, reason: str) -> ModuleResult:
        return ModuleResult(
            data={"target": target, "state": "unavailable", "source": source},
            findings=[
                make_finding(
                    self.name,
                    "RDNS: lookup unavailable",
                    {"target": target},
                    severity=Severity.LOW,
                    confidence=0.7,
                    evidence=reason,
                )
            ],
            meta={"source": source},
        )
