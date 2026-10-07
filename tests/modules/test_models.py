"""Normalizer/dedupe tests for core.models."""

from __future__ import annotations

import pytest

from core.constants import Severity
from core.exceptions import ValidationError
from core.models import (
    ModuleResult,
    content_hash,
    dedupe,
    make_finding,
    parse_findings,
    utc_now_iso,
)


def test_make_finding_defaults() -> None:
    finding = make_finding("whois", "registrant found")
    assert finding.module == "whois"
    assert finding.title == "registrant found"
    assert finding.data == {}
    assert finding.severity is Severity.INFO
    assert finding.confidence == 0.5
    assert finding.evidence == ""
    assert finding.collected_at
    assert finding.content_hash


def test_content_hash_is_stable_and_order_insensitive() -> None:
    a = make_finding(
        "dns", "record", {"a": 1, "b": 2}, severity=Severity.MEDIUM, confidence=0.8
    )
    b = make_finding(
        "dns", "record", {"b": 2, "a": 1}, severity=Severity.MEDIUM, confidence=0.8
    )
    assert content_hash(a) == content_hash(b) == a.content_hash == b.content_hash


def test_content_hash_ignores_collection_time() -> None:
    a = make_finding("http", "title", {"k": "v"}, collected_at=utc_now_iso())
    b = make_finding("http", "title", {"k": "v"}, collected_at=utc_now_iso())
    assert content_hash(a) == content_hash(b)


def test_content_hash_varies_with_content() -> None:
    a = make_finding("http", "title", {"k": "v"})
    b = make_finding("http", "title", {"k": "w"})
    assert content_hash(a) != content_hash(b)


def test_finding_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        make_finding("m", "t", confidence=1.5)
    with pytest.raises(ValidationError, match="confidence"):
        make_finding("m", "t", confidence=-0.1)


def test_finding_requires_module_and_title() -> None:
    with pytest.raises(ValidationError, match="module"):
        make_finding("", "t")
    with pytest.raises(ValidationError, match="title"):
        make_finding("m", "   ")


def test_finding_to_dict_shape() -> None:
    finding = make_finding(
        "dns", "a record", {"value": "1.2.3.4"}, severity=Severity.HIGH, confidence=0.9
    )
    payload = finding.to_dict()
    assert payload["module"] == "dns"
    assert payload["title"] == "a record"
    assert payload["severity"] == "high"
    assert payload["confidence"] == 0.9
    assert payload["data"] == {"value": "1.2.3.4"}
    assert payload["content_hash"] == finding.content_hash


def test_dedupe_preserves_order_and_removes_duplicates() -> None:
    a = make_finding("m", "same", {"k": 1})
    b = make_finding("m", "same", {"k": 1})
    c = make_finding("m", "different", {"k": 2})
    result = dedupe([a, b, c, a])
    assert result == [a, c]


def test_parse_findings_single_mapping() -> None:
    findings = parse_findings(
        "dns",
        {"title": "spf", "data": {"record": "v=spf1 -all"}, "severity": "low"},
    )
    assert len(findings) == 1
    assert findings[0].module == "dns"
    assert findings[0].severity is Severity.LOW
    assert findings[0].data == {"record": "v=spf1 -all"}


def test_parse_findings_sequence_and_skips_bad_items() -> None:
    findings = parse_findings(
        "http",
        [
            {"title": "tls", "data": {"ok": True}, "confidence": 0.7},
            {"data": {"no": "title"}},
            "bare text",
        ],
    )
    assert len(findings) == 1
    assert findings[0].title == "tls"


def test_parse_findings_wrapped_and_fallbacks() -> None:
    findings = parse_findings(
        "ssl",
        {"findings": [{"title": "cert", "data": {"cn": "x"}}]},
        severity=Severity.MEDIUM,
        confidence=0.6,
        evidence="scan artifact",
    )
    assert len(findings) == 1
    assert findings[0].severity is Severity.MEDIUM
    assert findings[0].confidence == 0.6
    assert findings[0].evidence == "scan artifact"


def test_parse_findings_empty() -> None:
    assert parse_findings("m", None) == []
    assert parse_findings("m", []) == []


def test_module_result_to_dict() -> None:
    finding = make_finding("m", "t", {"k": 1})
    result = ModuleResult(data={"target": "x"}, findings=[finding], meta={"m": 1})
    payload = result.to_dict()
    assert payload["data"] == {"target": "x"}
    assert payload["meta"] == {"m": 1}
    assert payload["findings"][0]["title"] == "t"
