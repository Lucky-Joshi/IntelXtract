"""Basic TLS certificate profiling for a domain (Phase 8, S8.3).

Performs a raw TLS handshake against port 443 using only the standard
library and reports subject, issuer, validity window, SAN list, and the
self-signed/expired flags.  Deep chain/trust analysis lands in Phase 13.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import ssl as _ssl
from datetime import UTC, datetime
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

_CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


def _rdn_pairs(components: Any) -> dict[str, list[str]]:
    """Flatten ``getpeercert()`` RDN components into ``{name: [values]}``."""
    out: dict[str, list[str]] = {}
    if not isinstance(components, tuple):
        return out
    for group in components:
        if not isinstance(group, tuple):
            continue
        for pair in group:
            if isinstance(pair, tuple) and len(pair) >= 2:
                out.setdefault(str(pair[0]), []).append(str(pair[1]))
    return out


def _common_names(pairs: dict[str, list[str]]) -> list[str]:
    return pairs.get("commonName", [])


def _parse_date(value: str) -> str:
    """Parse an OpenSSL ``notBefore``/``notAfter`` timestamp to ISO-8601."""
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value, _CERT_DATE_FORMAT)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat(timespec="seconds")


def _is_expired(not_after: str) -> bool:
    if "T" not in not_after:
        return False
    try:
        parsed = datetime.fromisoformat(not_after)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed < datetime.now(UTC)


def _normalize_cert(raw: dict[str, Any], host: str) -> dict[str, Any]:
    """Project ``getpeercert()`` into the module's flat certificate record."""
    subject = _rdn_pairs(raw.get("subject"))
    issuer = _rdn_pairs(raw.get("issuer"))
    sans = [
        entry[1]
        for entry in raw.get("subjectAltName", ())
        if isinstance(entry, tuple) and len(entry) == 2
    ]
    subject_cn = _common_names(subject)
    issuer_names = _common_names(issuer) or issuer.get("organizationName", [])
    not_before = _parse_date(str(raw.get("notBefore", "")))
    not_after = _parse_date(str(raw.get("notAfter", "")))
    return {
        "host": host,
        "subject_cn": subject_cn,
        "issuer": issuer_names or ["unknown"],
        "issued": not_before,
        "expires": not_after,
        "expired": _is_expired(not_after),
        "serial": str(raw.get("serialNumber", "")),
        "subject_alt_names": sans,
        "self_signed": bool(subject)
        and json.dumps(subject, sort_keys=True) == json.dumps(issuer, sort_keys=True),
    }


async def _get_peer_cert(
    host: str, *, port: int = 443, timeout_seconds: float = 10.0
) -> dict[str, Any] | None:
    """Connect to ``host`` and return the normalized peer certificate."""
    context = _ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = _ssl.CERT_NONE
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context, server_hostname=host),
            timeout=timeout_seconds,
        )
    except (TimeoutError, ConnectionError, OSError, _ssl.SSLError):
        return None
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        raw = ssl_object.getpeercert() if ssl_object is not None else None
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()
    if raw is None:
        return None
    return _normalize_cert(raw, host)


class SslModule(BaseModule):
    """Subject/issuer/validity/SAN metadata for a domain's TLS certificate."""

    name = "ssl"
    target_types = (TargetType.DOMAIN,)
    description = "basic TLS certificate metadata (subject, issuer, validity, SANs)"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        timeout_seconds = float(ctx.config.get("ssl.timeout", 10.0))
        cert = await _get_peer_cert(target, timeout_seconds=timeout_seconds)
        if cert is None:
            return ModuleResult(
                data={"target": target, "state": "unreachable"},
                findings=[
                    make_finding(
                        self.name,
                        "SSL: no TLS certificate reachable on port 443",
                        {"target": target, "state": "unreachable"},
                        severity=Severity.LOW,
                        confidence=0.8,
                        evidence="TLS handshake failed or timed out",
                    )
                ],
            )

        findings: list[Any] = [
            make_finding(
                self.name,
                "SSL: certificate",
                {
                    "subject_cn": cert["subject_cn"],
                    "issuer": cert["issuer"],
                    "issued": cert["issued"],
                    "expires": cert["expires"],
                    "self_signed": cert["self_signed"],
                },
                severity=Severity.INFO,
                confidence=0.9,
                evidence=f"{cert['subject_cn']} from {cert['issuer']}",
            ),
            make_finding(
                self.name,
                "SSL: subject alternative names",
                {"subject_alt_names": cert["subject_alt_names"]},
                severity=Severity.INFO,
                confidence=0.9,
                evidence=f"{len(cert['subject_alt_names'])} SAN(s)",
            ),
        ]
        if cert["self_signed"]:
            findings.append(
                make_finding(
                    self.name,
                    "SSL: self-signed certificate",
                    {"self_signed": True},
                    severity=Severity.MEDIUM,
                    confidence=0.9,
                    evidence="subject equals issuer",
                )
            )
        if cert["expired"]:
            findings.append(
                make_finding(
                    self.name,
                    "SSL: certificate expired",
                    {"expires": cert["expires"]},
                    severity=Severity.HIGH,
                    confidence=0.9,
                    evidence=f"expired at {cert['expires']}",
                )
            )
        return ModuleResult(
            data={"target": target, "certificate": cert}, findings=findings
        )
