"""Phase 17 — risk engine golden tests (S17.4) + engine wiring smoke test."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
from test_engine_correlation import _engine as _correlation_engine

from core.constants import ScanMode, ScanStatus
from core.risk import assess_risk, rating_for


def _finding(
    module: str, title: str, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"module": module, "title": title, "data": data or {}}


def _expired() -> dict[str, Any]:
    return _finding("ssl", "SSL: certificate expired", {"host": "example.com"})


def _self_signed() -> dict[str, Any]:
    return _finding("ssl", "SSL: self-signed certificate", {"host": "example.com"})


def _missing_header(name: str) -> dict[str, Any]:
    return _finding("headers", f"Headers: {name} missing", {"header": name})


def _insecure_cookie(*missing: str) -> dict[str, Any]:
    return _finding(
        "headers",
        "Headers: insecure cookie",
        {"cookie": "session", "missing": list(missing)},
    )


def test_rating_bands() -> None:
    assert rating_for(0.0) == "low"
    assert rating_for(24.9) == "low"
    assert rating_for(25.0) == "medium"
    assert rating_for(49.9) == "medium"
    assert rating_for(50.0) == "high"
    assert rating_for(74.9) == "high"
    assert rating_for(75.0) == "critical"
    assert rating_for(100.0) == "critical"


def test_empty_findings_score_zero_low() -> None:
    report = assess_risk([], target="example.com")
    assert report.score == 0.0
    assert report.rating == "low"
    assert report.rules == []
    assert report.categories["TLS"] == {"score": 0.0, "rules": 0}
    assert len(report.summary) == 1
    assert "No contributing risk findings" in report.summary[0]


def test_golden_score_and_traceable_rules() -> None:
    report = assess_risk(
        [
            _expired(),
            _missing_header("strict-transport-security"),
            _missing_header("content-security-policy"),
            _finding("dns", "DNS: no DMARC record"),
        ],
        target="example.com",
    )
    assert report.score == 59.0  # 35 + 9 + 9 + 6
    assert report.rating == "high"
    assert report.categories["TLS"]["score"] == 35.0
    assert report.categories["HEADERS"]["score"] == 18.0
    assert report.categories["DNS"]["score"] == 6.0
    assert report.categories["EXPOSURE"]["score"] == 0.0

    ids = [rule["rule_id"] for rule in report.rules]
    assert ids == ["tls_cert_expired", "headers_csp", "headers_hsts", "dns_no_dmarc"]
    assert report.rules[0]["points"] == 35.0
    assert report.rules[0]["finding"]["title"] == "SSL: certificate expired"
    for rule in report.rules:
        assert {"rule_id", "category", "label", "points", "finding"} <= rule.keys()

    verdict_line = report.summary[0]
    assert "HIGH (59/100)" in verdict_line


def test_category_ceiling_caps_tls_contribution() -> None:
    report = assess_risk([_expired(), _self_signed()], target="example.com")
    assert report.categories["TLS"]["score"] == 53.0  # raw sum is unbounded
    assert report.score == 40.0  # TLS contribution capped at 40
    assert report.rating == "medium"


def test_every_category_saturates_at_100() -> None:
    findings: list[dict[str, Any]] = [
        _expired(),
        _self_signed(),
        _finding("http", "HTTP: https unreachable"),
        _finding("http_methods", "HTTP: TRACE enabled"),
        _missing_header("strict-transport-security"),
        _missing_header("content-security-policy"),
        _missing_header("x-frame-options"),
        _missing_header("x-content-type-options"),
        _missing_header("referrer-policy"),
        _missing_header("permissions-policy"),
        _insecure_cookie("Secure", "HttpOnly"),
        _finding("headers", "Headers: server disclosure"),
        _finding("dns", "DNS: no DMARC record"),
        _finding("dns", "DNS: no SPF record"),
        _finding("whois", "RDAP: DNSSEC not signed"),
        _finding("email", "Email: domain accepts no mail (no MX)"),
        _finding("breach", "Breach: address exposed in known breach(es)"),
        _finding("metadata", "Metadata: GPS coordinates"),
        _finding("email", "Email: disposable address"),
    ]
    report = assess_risk(findings, target="example.com")
    assert report.score == 100.0
    assert report.rating == "critical"


def test_cookie_secure_flag_weight() -> None:
    weak = assess_risk([_insecure_cookie("HttpOnly")], target="example.com")
    strong = assess_risk([_insecure_cookie("Secure")], target="example.com")
    assert weak.score == 2.0
    assert strong.score == 7.0


def test_weak_spf_dmarc_rules() -> None:
    spf_weak = _finding("email", "Email: SPF policy", {"domain": "d", "all": "+all"})
    spf_strong = _finding("email", "Email: SPF policy", {"domain": "d", "all": "-all"})
    dmarc_none = _finding(
        "email", "Email: DMARC policy", {"domain": "d", "policy": "none"}
    )
    dmarc_quarantine = _finding(
        "email", "Email: DMARC policy", {"domain": "d", "policy": "quarantine"}
    )

    assert assess_risk([spf_weak], target="example.com").score == 6.0
    assert assess_risk([spf_strong], target="example.com").score == 0.0
    assert assess_risk([dmarc_none], target="example.com").score == 6.0
    assert assess_risk([dmarc_quarantine], target="example.com").score == 0.0


def test_deterministic_across_input_order() -> None:
    findings: list[dict[str, Any]] = [
        _expired(),
        _missing_header("strict-transport-security"),
        _finding("dns", "DNS: no DMARC record"),
        _insecure_cookie("Secure"),
        _finding("breach", "Breach: address exposed in known breach(es)"),
    ]
    baseline = assess_risk(findings, target="example.com").to_dict()

    rng = random.Random(17)  # noqa: S311 (test-only shuffle, non-cryptographic)
    for _ in range(20):
        shuffled = findings[:]
        rng.shuffle(shuffled)
        assert assess_risk(shuffled, target="example.com").to_dict() == baseline


def test_summary_lists_top_risks_in_plain_language() -> None:
    report = assess_risk(
        [
            _expired(),
            _insecure_cookie("Secure"),
            _finding("dns", "DNS: no DMARC record"),
        ],
        target="example.com",
    )
    assert report.summary[0].startswith("Overall risk:")
    assert any("TLS certificate has expired" in line for line in report.summary)
    assert any("Cookie set without the Secure flag" in line for line in report.summary)


async def test_scan_carries_stable_risk_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_a = await _correlation_engine(tmp_path, monkeypatch)
    engine_b = await _correlation_engine(tmp_path, monkeypatch)

    scan_a = await engine_a.scan("example.com", mode=ScanMode.DEEP)
    scan_b = await engine_b.scan("example.com", mode=ScanMode.DEEP)

    assert scan_a.status is ScanStatus.COMPLETED
    risk = scan_a.risk
    assert risk is not None
    assert {
        "target",
        "score",
        "rating",
        "categories",
        "rules",
        "summary",
    } <= risk.keys()
    assert risk["target"] == "example.com"
    assert 0.0 <= risk["score"] <= 100.0
    assert risk["rating"] == rating_for(risk["score"])
    assert risk == scan_b.risk
    assert scan_a.to_dict()["risk"] == risk
