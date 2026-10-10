"""Certificate chain parsing and detail extraction (Phase 13, S13.1).

Performs no network I/O: it turns PEM/DER certificate bytes (captured
fixtures or bytes handed in from the collector) into a flat, JSON-friendly
record — subject/issuer DNs, SAN enumeration, signature algorithm, serial,
validity, key/extended-key usage, CA flag, CT poison mark, and SCT list.
``fetch_peer_chain`` is the only live-network function and is deliberately
separate so unit tests never touch TLS.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl as _ssl
from datetime import UTC, datetime
from typing import Any, cast

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID

_WEAK_SIGNATURE_NAMES = frozenset({"md5", "sha1"})
_EXPIRY_WARNING_DAYS = 30
# RFC 6962 SCT-list extension (precertificate poison / embedded SCTs).
_COUNTERSIGNATURE_OIDS = frozenset(
    {
        "1.3.6.1.4.1.11129.2.4.2",
        "1.3.6.1.4.1.11129.2.4.3",
        "1.3.6.1.4.1.11129.2.4.5",
    }
)


class CertificateParseError(ValueError):
    """Raised when a packet cannot be decoded as an X.509 certificate."""


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _dn_parts(name: x509.Name) -> dict[str, list[str]]:
    """Flatten an X.509 Name into ``{attribute: [values...]}`` preserving order."""
    parts: dict[str, list[str]] = {}
    for attribute in name.rdns:
        for attr in attribute:
            key = attr.oid._name if attr.oid._name else attr.oid.dotted_string
            parts.setdefault(key, []).append(str(attr.value))
    return parts


def _san_strings(cert: x509.Certificate) -> list[str]:
    """SAN values rendered as ``Type:value`` (``DNS:example.com``)."""
    try:
        names = cast(
            x509.SubjectAlternativeName,
            cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            ).value,
        )
    except x509.ExtensionNotFound:
        return []
    entries: list[str] = []
    for name in names:
        if isinstance(name, x509.DNSName):
            entries.append(f"DNS:{name.value}")
        elif isinstance(name, x509.IPAddress):
            entries.append(f"IP:{name.value}")
        elif isinstance(name, x509.RFC822Name):
            entries.append(f"email:{name.value}")
        elif isinstance(name, x509.UniformResourceIdentifier):
            entries.append(f"URI:{name.value}")
        else:
            entries.append(f"other:{name.value}")
    return entries


def _scts(cert: x509.Certificate) -> list[dict[str, Any]]:
    """Precert/SCT evidence: version, log id, transaction timestamp."""
    for oid in _COUNTERSIGNATURE_OIDS:
        try:
            ext = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(oid))
        except x509.ExtensionNotFound:
            continue
        value = ext.value
        lines: list[dict[str, Any]] = []
        try:
            for entry in value:  # type: ignore[attr-defined]
                log_id = getattr(entry, "log_id", b"")
                raw_version = getattr(entry, "version", 0)
                lines.append(
                    {
                        "version": (
                            int(raw_version)
                            if isinstance(raw_version, int)
                            else str(getattr(raw_version, "value", raw_version))
                        ),
                        "log_id": (
                            log_id.hex() if isinstance(log_id, bytes) else str(log_id)
                        ),
                        "timestamp": _iso(
                            getattr(entry, "timestamp", datetime.fromtimestamp(0, UTC))
                        ),
                    }
                )
        except TypeError:
            return lines
        return lines
    return []


def normalize_x509(cert: x509.Certificate) -> dict[str, Any]:
    """Project one parsed X.509 certificate onto IntelXtract's record shape."""
    subject = _dn_parts(cert.subject)
    issuer = _dn_parts(cert.issuer)
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc
    signature_oid = cert.signature_algorithm_oid
    sig_name = (
        signature_oid._name if signature_oid._name else signature_oid.dotted_string
    )

    try:
        key_usage = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        ku: list[str] = []
        for attr in (
            "digital_signature",
            "content_commitment",
            "key_encipherment",
            "data_encipherment",
            "key_agreement",
            "key_cert_sign",
            "crl_sign",
            "encipher_only",
            "decipher_only",
        ):
            if getattr(key_usage, attr, False):
                ku.append(attr.replace("_", "-"))
    except x509.ExtensionNotFound:
        ku = []

    try:
        eku_ext = cast(
            x509.ExtendedKeyUsage,
            cert.extensions.get_extension_for_oid(
                ExtensionOID.EXTENDED_KEY_USAGE
            ).value,
        )
        eku = [oid._name if oid._name else oid.dotted_string for oid in eku_ext]
    except x509.ExtensionNotFound:
        eku = []

    try:
        ct_poison = bool(
            cert.extensions.get_extension_for_oid(
                x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.4.3")
            ).value
        )
    except x509.ExtensionNotFound:
        ct_poison = False

    try:
        sct_list = cert.extensions.get_extension_for_oid(
            x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.4.2")
        )
        ct_scts = bool(sct_list)
    except x509.ExtensionNotFound:
        ct_scts = False

    try:
        constraints = cast(
            x509.BasicConstraints,
            cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value,
        )
        is_ca = bool(constraints.ca)
    except x509.ExtensionNotFound:
        is_ca = False

    return {
        "subject": subject,
        "issuer": issuer,
        "serial": f"{cert.serial_number:x}",
        "not_before": _iso(not_before),
        "not_after": _iso(not_after),
        "expired": not_after < datetime.now(UTC),
        "days_remaining": (not_after - datetime.now(UTC)).days,
        "signature_algorithm": sig_name.lower(),
        "subject_alt_names": _san_strings(cert),
        "key_usage": ku,
        "extended_key_usage": eku,
        "is_ca": is_ca,
        "ct_poison": ct_poison,
        "ct_scts": ct_scts,
        "scts": _scts(cert),
        "self_signed": subject == issuer,
        "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
    }


def parse_pem(pem_bytes: bytes) -> list[dict[str, Any]]:
    """Parse one or more PEM certificates into normalized records."""
    try:
        certs = x509.load_pem_x509_certificates(pem_bytes)
    except ValueError as exc:
        raise CertificateParseError(f"invalid PEM certificate(s): {exc}") from exc
    return [normalize_x509(cert) for cert in certs]


def parse_der(der_bytes: bytes) -> dict[str, Any]:
    """Parse a single DER-encoded certificate into a normalized record."""
    try:
        cert = x509.load_der_x509_certificate(der_bytes)
    except ValueError as exc:
        raise CertificateParseError(f"invalid DER certificate: {exc}") from exc
    return normalize_x509(cert)


def _expires_too_soon(record: dict[str, Any]) -> bool:
    return (
        isinstance(record.get("days_remaining"), int)
        and record["days_remaining"] <= _EXPIRY_WARNING_DAYS
        and record["days_remaining"] > 0
    )


def classify_cert(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Risk findings for a single normalized certificate (pure, tested).

    Returns plain dicts shaped like findings; the collector converts them
    with ``make_finding``.  Keeping this I/O-free lets the risk logic be
    unit-tested against fixture certificates without a live TLS connection.
    """
    risk: list[dict[str, Any]] = []
    sig = str(record.get("signature_algorithm", "")).lower()
    if any(weak in sig for weak in _WEAK_SIGNATURE_NAMES):
        risk.append(
            {
                "title": "Certificate: weak signature algorithm",
                "data": {"signature_algorithm": record.get("signature_algorithm", "")},
                "severity": "medium",
                "evidence": f"signature uses {sig}",
            }
        )
    if record.get("expired", False) or record.get("days_remaining", 0) < 0:
        risk.append(
            {
                "title": "Certificate: expired",
                "data": {"not_after": record.get("not_after", "")},
                "severity": "high",
                "evidence": (f"certificate expired {record.get('not_after', '')}"),
            }
        )
    elif _expires_too_soon(record):
        risk.append(
            {
                "title": "Certificate: expiring soon",
                "data": {
                    "not_after": record.get("not_after", ""),
                    "days_remaining": record.get("days_remaining", 0),
                },
                "severity": "medium",
                "evidence": f"renewal due ({(record.get('days_remaining'))} day(s))",
            }
        )
    if record.get("self_signed"):
        risk.append(
            {
                "title": "Certificate: self-signed",
                "data": {"self_signed": True},
                "severity": "medium",
                "evidence": "subject equals issuer",
            }
        )
    if record.get("ct_poison"):
        risk.append(
            {
                "title": "Certificate: precertificate (CT poison)",
                "data": {"ct_poison": True},
                "severity": "low",
                "evidence": "legitimate precert; logger certs may be rejected",
            }
        )
    return risk


async def fetch_peer_chain(
    host: str,
    *,
    port: int = 443,
    timeout_seconds: float = 10.0,
) -> list[bytes]:
    """DER leaf certificate presented by ``host`` (live, optional-only).

    The standard-library TLS API exposes only the validated leaf; chain
    depth/issuer history for the rest is reconstructed via certificate
    transparency (``modules.certificate.transparency``).  Returns ``[]``
    when no TLS peer certificate is reachable.
    """
    context = _ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = _ssl.CERT_NONE
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context, server_hostname=host),
            timeout=timeout_seconds,
        )
    except (
        TimeoutError,
        ConnectionError,
        OSError,
        _ssl.SSLError,
        asyncio.CancelledError,
    ):
        return []
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        der = (
            ssl_object.getpeercert(binary_form=True) if ssl_object is not None else None
        )
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()
    return [der] if der else []


__all__ = [
    "CertificateParseError",
    "classify_cert",
    "fetch_peer_chain",
    "normalize_x509",
    "parse_der",
    "parse_pem",
]
