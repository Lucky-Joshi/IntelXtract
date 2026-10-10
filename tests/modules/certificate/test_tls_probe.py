"""TLS protocol/cipher classification tests (Phase 13, S13.2).

``classify_tls``/``weak_cipher`` are pure — probe reports are synthetic
dicts, so these tests never perform a handshake.
"""

from __future__ import annotations

from typing import Any

from modules.certificate.tls_probe import classify_tls, weak_cipher


def _report(
    versions: list[tuple[str, bool, str | None]],
    *,
    host: str = "example.com",
) -> dict[str, Any]:
    entries = [
        {"version": name, "supported": supported, "cipher": cipher, "reason": ""}
        for name, supported, cipher in versions
    ]
    supported_entries = [entry for entry in entries if entry["supported"]]
    return {
        "host": host,
        "versions": entries,
        "negotiated": supported_entries[-1] if supported_entries else None,
    }


def test_supported_versions_summary_is_emitted() -> None:
    report = _report(
        [("TLSv1", False, None), ("TLSv1.2", True, "ECDHE-RSA-AES128-GCM-SHA256")]
    )

    findings = classify_tls(report)

    summary = next(
        item for item in findings if item["title"] == "TLS: supported protocol versions"
    )
    assert summary["severity"] == "info"
    assert summary["data"]["versions"] == ["TLSv1.2"]


def test_legacy_protocol_versions_raise_medium_findings() -> None:
    report = _report(
        [
            ("TLSv1", True, "ECDHE-RSA-AES128-SHA"),
            ("TLSv1.1", True, "ECDHE-RSA-AES128-SHA"),
            ("TLSv1.2", True, "ECDHE-RSA-AES128-GCM-SHA256"),
            ("TLSv1.3", False, None),
        ]
    )

    findings = classify_tls(report)
    weak = [item for item in findings if item["title"] == "TLS: weak protocol version"]

    assert len(weak) == 2
    assert {item["data"]["version"] for item in weak} == {"TLSv1", "TLSv1.1"}
    assert all(item["severity"] == "medium" for item in weak)


def test_weak_negotiated_cipher_raises_finding() -> None:
    report = _report([("TLSv1.2", True, "ECDHE-RSA-DES-CBC3-SHA")])

    findings = classify_tls(report)

    cipher_finding = next(
        item for item in findings if item["title"] == "TLS: weak cipher suite"
    )
    assert cipher_finding["severity"] == "medium"
    assert cipher_finding["data"]["cipher"] == "ECDHE-RSA-DES-CBC3-SHA"
    negotiated = next(
        item for item in findings if item["title"] == "TLS: negotiated cipher"
    )
    assert negotiated["severity"] == "info"


def test_modern_only_report_has_no_weak_findings() -> None:
    report = _report(
        [("TLSv1.2", True, "ECDHE-RSA-AES128-GCM-SHA256"), ("TLSv1.3", True, None)]
    )

    findings = classify_tls(report)
    titles = [item["title"] for item in findings]

    assert "TLS: weak protocol version" not in titles
    assert "TLS: weak cipher suite" not in titles
    assert "TLS: supported protocol versions" in titles


def test_empty_report_does_not_crash() -> None:
    findings = classify_tls({"host": "example.com", "versions": [], "negotiated": None})

    assert findings == []
    assert classify_tls({"host": "example.com"}) == []


def test_weak_cipher_marker_detection() -> None:
    assert weak_cipher("ECDHE-RSA-RC4-SHA") is True
    assert weak_cipher("ECDHE-RSA-DES-CBC3-SHA") is True
    assert weak_cipher("AES128-SHA256") is False
    assert weak_cipher("TLS_AES_256_GCM_SHA384") is False
    assert weak_cipher(None) is False
    assert weak_cipher("") is False
