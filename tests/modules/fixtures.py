"""Static, hand-recorded fixtures for Phase 8 network modules (no I/O).

Each JSON file mirrors a real upstream response shape (RDAP, DoH JSON,
crt.sh, HTTP probes) so the domain-module tests exercise realistic payloads
without touching the network.  ``doh_handler``/``http_handler`` produce the
callable ``(status, headers, body)`` stubs consumed by
:class:`fakes.FakeHttpClient`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any, cast

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

StubHandler = Callable[[str, str, dict[str, Any]], tuple[int, dict[str, str], Any]]


@cache
def _load(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def rdap_payload() -> dict[str, Any]:
    """RDAP response for ``example.com`` (whois module)."""
    return cast(dict[str, Any], _load("rdap.json"))


def crt_payload() -> list[dict[str, Any]]:
    """crt.sh JSON entries for ``example.com`` (subdomain module)."""
    return cast(list[dict[str, Any]], _load("crt.json"))


def geo_payload() -> dict[str, Any]:
    """ip-api.org success payload for ``1.1.1.1`` (geo module)."""
    return cast(dict[str, Any], _load("geo.json"))


def tech_html() -> str:
    """Corpus page with WordPress/jQuery/Bootstrap markers (tech module)."""
    return cast(str, (FIXTURE_DIR / "tech.html").read_text(encoding="utf-8"))


def robots_txt() -> str:
    """robots.txt exercising group/disallow parsing (robots module)."""
    return cast(str, (FIXTURE_DIR / "robots.txt").read_text(encoding="utf-8"))


def sitemap_xml() -> str:
    """sitemap.xml with three <loc> entries (robots module)."""
    return cast(str, (FIXTURE_DIR / "sitemap.xml").read_text(encoding="utf-8"))


def favicon_bytes() -> bytes:
    """Deterministic favicon payload for fingerprint tests."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"idat-corpus-icon" * 8


# --- captured certificate fixtures (Phase 13, no live TLS) -------------------

_CT_POISON_OID = "1.3.6.1.4.1.11129.2.4.3"


def make_cert_pem(
    *,
    subject_cn: str = "example.com",
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    sans: Sequence[str] = (),
    is_ca: bool = False,
    ct_poison: bool = False,
    serial: int | None = None,
) -> bytes:
    """Build a deterministic self-signed certificate PEM (offline fixture).

    Every Phase 13 certificate test parses these bytes instead of opening a
    live TLS connection; validity windows are explicit so expired/expiring
    states are reproducible.
    """
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    key = ec.generate_private_key(ec.SECP256R1())
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial if serial is not None else x509.random_serial_number())
        .not_valid_before(not_before or (now - timedelta(days=1)))
        .not_valid_after(not_after or (now + timedelta(days=365)))
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
    )
    if sans:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(entry) for entry in sans]),
            critical=False,
        )
    if ct_poison:
        builder = builder.add_extension(
            x509.UnrecognizedExtension(
                x509.ObjectIdentifier(_CT_POISON_OID), b"\x05\x00"
            ),
            critical=False,
        )
    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM)


def doh_answer(data: str, *, rtype: int = 1, name: str = "") -> dict[str, Any]:
    """Build a minimal DoH JSON response carrying one answer record."""
    return cast(
        dict[str, Any],
        {
            "Status": 0,
            "Answer": [{"name": name, "type": rtype, "TTL": 60, "data": data}],
        },
    )


def doh_handler() -> StubHandler:
    """DoH JSON responses keyed by ``(name, type)`` query pair (dns module)."""
    table: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _load("doh.json"):
        query = item["query"]
        table[(query["name"], query["type"])] = item["response"]

    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        params = kwargs.get("params") or {}
        name = params.get("name")
        dns_type = params.get("type")
        key = (
            name if isinstance(name, str) else "",
            dns_type if isinstance(dns_type, str) else "",
        )
        response = table.get(key)
        if response is None:
            return 200, {"content-type": "application/dns-json"}, {"Status": 0}
        return 200, {"content-type": "application/dns-json"}, response

    return _handle


def http_handler() -> StubHandler:
    """HTTP probe responses keyed by exact URL (http module)."""
    table = _load("http.json")

    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        entry = table.get(url)
        if entry is None:
            return 404, {"content-type": "text/plain"}, "not found"
        return entry["status"], entry["headers"], entry["body"]

    return _handle
