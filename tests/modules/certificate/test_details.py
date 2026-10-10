"""Certificate detail parsing + risk classification (Phase 13, S13.1/S13.4).

All certificates are built offline from :func:`fixtures.make_cert_pem` —
no unit test in this package ever opens a TLS connection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fixtures import make_cert_pem
from modules.certificate.details import (
    CertificateParseError,
    classify_cert,
    normalize_x509,
    parse_der,
    parse_pem,
)


def _record_with_signature(signature: str) -> dict[str, Any]:
    """Copy of a fixture record with the signature algorithm overridden.

    ``cryptography`` refuses to *create* SHA-1 signatures, so the weak-sig
    path is exercised on the classification layer where the algorithm name
    is just data.
    """
    record = parse_pem(make_cert_pem(subject_cn="weak.example.com"))[0]
    record["signature_algorithm"] = signature
    return record


def test_parse_pem_extracts_core_fields() -> None:
    pem = make_cert_pem(
        subject_cn="example.com",
        sans=("example.com", "www.example.com"),
    )
    records = parse_pem(pem)

    assert len(records) == 1
    record = records[0]
    assert record["subject"]["commonName"] == ["example.com"]
    assert record["issuer"]["commonName"] == ["example.com"]
    assert record["subject_alt_names"] == [
        "DNS:example.com",
        "DNS:www.example.com",
    ]
    assert record["signature_algorithm"] == "ecdsa-with-sha256"
    assert record["not_before"].endswith("+00:00")
    assert record["expired"] is False
    assert record["days_remaining"] > 0
    assert record["is_ca"] is False
    assert record["ct_poison"] is False
    assert record["self_signed"] is True
    assert len(record["serial"]) > 4
    assert len(record["fingerprint_sha256"]) == 64


def test_parse_pem_chain_returns_all_certificates() -> None:
    first = make_cert_pem(subject_cn="root.example.com", is_ca=True)
    second = make_cert_pem(subject_cn="leaf.example.com")
    chain = first + second

    records = parse_pem(chain)

    assert len(records) == 2
    assert records[0]["subject"]["commonName"] == ["root.example.com"]
    assert records[1]["subject"]["commonName"] == ["leaf.example.com"]
    assert records[0]["is_ca"] is True
    assert records[1]["is_ca"] is False


def test_parse_pem_rejects_garbage() -> None:
    with pytest.raises(CertificateParseError):
        parse_pem(b"-----BEGIN CERTIFICATE-----\nnot-a-cert\n-----END-----")


def test_parse_der_round_trip() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    pem = make_cert_pem(subject_cn="der.example.com", sans=("der.example.com",))
    der = x509.load_pem_x509_certificate(pem).public_bytes(Encoding.DER)

    record = parse_der(der)

    assert record["subject"]["commonName"] == ["der.example.com"]
    assert record["subject_alt_names"] == ["DNS:der.example.com"]
    with pytest.raises(CertificateParseError):
        parse_der(b"\x30\x03\x01\x01\x00")


def test_parse_der_rejects_invalid_bytes() -> None:
    with pytest.raises(CertificateParseError):
        parse_der(b"\x30\x03\x01\x01\x00")


def test_expired_certificate_flagged() -> None:
    now = datetime.now(UTC)
    pem = make_cert_pem(
        subject_cn="expired.example.com",
        not_before=now - timedelta(days=400),
        not_after=now - timedelta(days=30),
    )
    record = parse_pem(pem)[0]

    assert record["expired"] is True
    assert record["days_remaining"] < 0

    titles = {item["title"] for item in classify_cert(record)}
    expired = next(
        item
        for item in classify_cert(record)
        if item["title"] == "Certificate: expired"
    )
    assert expired["severity"] == "high"
    assert "Certificate: expiring soon" not in titles


def test_expiring_soon_certificate_flagged() -> None:
    now = datetime.now(UTC)
    pem = make_cert_pem(
        subject_cn="soon.example.com",
        not_before=now - timedelta(days=355),
        not_after=now + timedelta(days=10),
    )
    record = parse_pem(pem)[0]

    items = classify_cert(record)
    expiring = [item for item in items if item["title"] == "Certificate: expiring soon"]
    assert len(expiring) == 1
    assert expiring[0]["severity"] == "medium"
    assert expiring[0]["data"]["days_remaining"] == record["days_remaining"]
    assert not any(item["title"] == "Certificate: expired" for item in items)


def test_ca_and_ct_poison_flags() -> None:
    ca_pem = make_cert_pem(subject_cn="ca.example.com", is_ca=True)
    poison_pem = make_cert_pem(subject_cn="pre.example.com", ct_poison=True)

    ca_record = parse_pem(ca_pem)[0]
    poison_record = parse_pem(poison_pem)[0]

    assert ca_record["is_ca"] is True
    assert poison_record["ct_poison"] is True
    poison_items = classify_cert(poison_record)
    assert any(
        item["title"] == "Certificate: precertificate (CT poison)"
        and item["severity"] == "low"
        for item in poison_items
    )


def test_classify_weak_signature_from_record() -> None:
    record = _record_with_signature("sha1withrsaencryption")

    items = classify_cert(record)
    weak = [
        item
        for item in items
        if item["title"] == "Certificate: weak signature algorithm"
    ]
    assert len(weak) == 1
    assert weak[0]["severity"] == "medium"


def test_classify_healthy_certificate_has_no_risk_items() -> None:
    pem = make_cert_pem(subject_cn="healthy.example.com")
    record = parse_pem(pem)[0]

    # Fixture certs are self-signed, which is the only risk finding expected.
    items = classify_cert(record)
    assert [item["title"] for item in items] == ["Certificate: self-signed"]


def test_normalize_accepts_certificate_object() -> None:
    from cryptography import x509

    pem = make_cert_pem(subject_cn="obj.example.com")
    cert = x509.load_pem_x509_certificate(pem)

    record = normalize_x509(cert)

    assert record["subject"]["commonName"] == ["obj.example.com"]
