"""Certificate module entry point (Phase 13, S13.1-S13.4).

Orchestrates the three certificate intelligence sources: peer-certificate
detail parsing (live handshake), a TLS protocol/cipher probe (live), and
crt.sh transparency history (passive, via the shared HTTP client).  The
live hooks are module-level functions so tests stub them and never open a
real TLS connection.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import Finding, ModuleResult, make_finding
from modules.base import BaseModule
from modules.certificate import details, tls_probe
from modules.certificate.transparency import fetch_transparency


async def fetch_chain_records(
    host: str, *, timeout_seconds: float
) -> list[dict[str, Any]]:
    """Live handshake + parse; monkeypatched in unit tests."""
    chain_der = await details.fetch_peer_chain(host, timeout_seconds=timeout_seconds)
    records: list[dict[str, Any]] = []
    for der in chain_der:
        try:
            records.append(details.parse_der(der))
        except details.CertificateParseError:
            continue
    return records


async def probe_protocol(host: str, *, timeout_seconds: float) -> dict[str, Any]:
    """Live TLS version/cipher probe; monkeypatched in unit tests."""
    return await tls_probe.probe_tls(host, timeout_seconds=timeout_seconds)


class CertificateModule(BaseModule):
    """Deep TLS/certificate intelligence: chain details, TLS probe, CT."""

    name = "certificate"
    target_types = (TargetType.DOMAIN,)
    description = "TLS certificate chain, protocol/cipher probe, CT history"
    timeout = 45.0

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        timeout_seconds = float(ctx.config.get("certificate.timeout", 10.0))
        max_results = int(ctx.config.get("certificate.max_results", 100))

        records = await fetch_chain_records(target, timeout_seconds=timeout_seconds)
        report = await probe_protocol(target, timeout_seconds=timeout_seconds)
        transparency = await fetch_transparency(
            self, ctx, target, max_results=max_results
        )

        findings: list[Finding] = []
        state = "ok"
        if not records and not transparency.get("count"):
            state = "unknown"
        elif not records:
            state = "partial"

        for record in records:
            findings.extend(
                make_finding(
                    self.name,
                    item["title"],
                    item["data"],
                    severity=Severity(item["severity"]),
                    confidence=0.8,
                    evidence=item["evidence"],
                )
                for item in details.classify_cert(record)
            )
            sans = record.get("subject_alt_names", [])
            if sans:
                findings.append(
                    make_finding(
                        self.name,
                        "Certificate: subject alternative names",
                        {
                            "subject_alt_names": sans,
                            "subject": record.get("subject", {}),
                            "serial": record.get("serial", ""),
                        },
                        severity=Severity.INFO,
                        confidence=0.9,
                        evidence=f"{len(sans)} SAN(s)",
                    )
                )
            findings.append(
                make_finding(
                    self.name,
                    "Certificate: chain details",
                    {
                        "subject": record.get("subject", {}),
                        "issuer": record.get("issuer", {}),
                        "serial": record.get("serial", ""),
                        "not_before": record.get("not_before", ""),
                        "not_after": record.get("not_after", ""),
                        "signature_algorithm": record.get("signature_algorithm", ""),
                        "is_ca": record.get("is_ca", False),
                        "ct_scts": record.get("ct_scts", False),
                    },
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"serial {record.get('serial', '')}",
                )
            )

        if report.get("versions"):
            findings.extend(
                make_finding(
                    self.name,
                    item["title"],
                    item["data"],
                    severity=Severity(item["severity"]),
                    confidence=0.8,
                    evidence=item["evidence"],
                )
                for item in tls_probe.classify_tls(report)
            )

        if transparency.get("count"):
            findings.append(
                make_finding(
                    self.name,
                    "Certificate: transparency history",
                    {
                        "count": transparency["count"],
                        "issuers": transparency["issuers"],
                        "first_seen": transparency["first_seen"],
                        "last_seen": transparency["last_seen"],
                        "related_names": transparency["related_names"],
                    },
                    severity=Severity.INFO,
                    confidence=0.7,
                    evidence=f"{transparency['count']} certificate(s) in CT logs",
                )
            )
        else:
            findings.append(
                make_finding(
                    self.name,
                    "Certificate: transparency history unavailable",
                    {"target": target, "count": 0},
                    severity=Severity.LOW,
                    confidence=0.5,
                    evidence="crt.sh returned no entries (offline or no history)",
                )
            )

        data: dict[str, Any] = {
            "target": target,
            "state": state,
            "certificates": records,
            "tls": report,
            "transparency": transparency,
        }
        return ModuleResult(
            data=data,
            findings=findings,
            meta={"source": "peer+crt.sh" if transparency.get("count") else "peer"},
        )
