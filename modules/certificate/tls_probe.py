"""TLS protocol/cipher probe (Phase 13, S13.2).

Handshakes against a target with each supported protocol version (TLS 1.0
through 1.3) and records which are accepted plus the negotiated cipher.
``probe_tls`` performs the live handshakes (only when the collector runs);
:class:`classify_tls` turns the structured probe report into weak-protocol
and weak-cipher findings and is pure, so unit tests never touch a network.
"""

from __future__ import annotations

import asyncio
import ssl as _ssl
from typing import Any

_WEAK_PROTOCOLS = frozenset({"TLSv1", "TLSv1.1"})
_WEAK_CIPHER_MARKERS = ("rc4", "3des", "cbc", "null", "export")
_VERSION_TO_MIN = {
    "TLSv1": _ssl.TLSVersion.TLSv1,
    "TLSv1.1": _ssl.TLSVersion.TLSv1_1,
    "TLSv1.2": _ssl.TLSVersion.TLSv1_2,
    "TLSv1.3": _ssl.TLSVersion.TLSv1_3,
}


def _build_context(version: _ssl.TLSVersion) -> _ssl.SSLContext:
    """Client context pinned to exactly ``version`` (may be rejected locally)."""
    context = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = _ssl.CERT_NONE
    # Fresh SSLContext defaults clear OP_NO_* flags; pin both ends.
    context.minimum_version = version
    context.maximum_version = version
    return context


async def _probe_version(
    host: str, version: str, port: int, timeout_seconds: float
) -> dict[str, Any]:
    """One handshake attempt for ``version``; never raises."""
    label = version
    target_version = _VERSION_TO_MIN[version]
    try:
        context = _build_context(target_version)
    except ValueError:
        return {
            "version": label,
            "supported": False,
            "cipher": None,
            "reason": "unsupported",
        }
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context, server_hostname=host),
            timeout=timeout_seconds,
        )
    except (TimeoutError, ConnectionError, OSError, _ssl.SSLError):
        return {
            "version": label,
            "supported": False,
            "cipher": None,
            "reason": "refused",
        }
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        cipher_info = ssl_object.cipher() if ssl_object is not None else None
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except (OSError, _ssl.SSLError):
            pass
    if cipher_info is None:
        return {
            "version": label,
            "supported": False,
            "cipher": None,
            "reason": "no cipher",
        }
    return {"version": label, "supported": True, "cipher": cipher_info[0], "reason": ""}


async def probe_tls(
    host: str,
    *,
    port: int = 443,
    versions: tuple[str, ...] = ("TLSv1", "TLSv1.1", "TLSv1.2", "TLSv1.3"),
    timeout_seconds: float = 6.0,
) -> dict[str, Any]:
    """Probe each protocol version against ``host`` (live network).

    Results are ordered by version for a stable report shape:
    ``{"host", "versions": [...], "negotiated": {...} | None}``.
    """
    attempts = [
        await _probe_version(host, version, port, timeout_seconds)
        for version in versions
    ]
    supported = [item for item in attempts if item["supported"]]
    negotiated = supported[-1] if supported else None
    return {"host": host, "versions": attempts, "negotiated": negotiated}


def weak_cipher(cipher: str | None) -> bool:
    """True when the negotiated cipher name signals a deprecated primitive."""
    if not cipher:
        return False
    lowered = cipher.lower()
    return any(marker in lowered for marker in _WEAK_CIPHER_MARKERS)


def classify_tls(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a probe report into findings (pure; tested offline)."""
    findings: list[dict[str, Any]] = []
    versions = report.get("versions", [])
    if not versions:
        return findings
    supported_names = [v["version"] for v in versions if v.get("supported")]
    findings.append(
        {
            "title": "TLS: supported protocol versions",
            "data": {"versions": supported_names, "host": report.get("host", "")},
            "severity": "info",
            "evidence": f"{len(supported_names)} protocol version(s) accepted",
        }
    )
    for entry in versions:
        if not entry.get("supported"):
            continue
        if entry["version"] in _WEAK_PROTOCOLS:
            findings.append(
                {
                    "title": "TLS: weak protocol version",
                    "data": {
                        "version": entry["version"],
                        "host": report.get("host", ""),
                    },
                    "severity": "medium",
                    "evidence": f"{entry['version']} is deprecated",
                }
            )
    negotiated = report.get("negotiated")
    if negotiated:
        cipher = negotiated.get("cipher")
        if weak_cipher(cipher):
            findings.append(
                {
                    "title": "TLS: weak cipher suite",
                    "data": {"cipher": cipher, "host": report.get("host", "")},
                    "severity": "medium",
                    "evidence": f"negotiated {cipher}",
                }
            )
        findings.append(
            {
                "title": "TLS: negotiated cipher",
                "data": {"cipher": cipher, "version": negotiated.get("version")},
                "severity": "info",
                "evidence": f"{negotiated.get('version')} / {cipher}",
            }
        )
    return findings


__all__ = ["classify_tls", "probe_tls", "weak_cipher"]
