"""Phase 19 — report model builder tests (S19.6: golden JSON snapshot)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reports import build_report

GENERATED_AT = "2026-10-10T12:00:00"

GOLDEN = Path(__file__).parent / "golden" / "report.json"


def sample_target() -> dict[str, Any]:
    return {"value": "example.com", "type": "domain"}


def sample_scan() -> dict[str, Any]:
    return {
        "id": 7,
        "uuid": "u7",
        "mode": "deep",
        "status": "completed",
        "started_at": 1_709_836_800.0,
        "finished_at": 1_709_836_860.0,
        "duration": 60.0,
        "error": None,
        "runs": [{"module": "dns", "status": "ok", "duration": 0.5}],
    }


def sample_findings() -> list[dict[str, Any]]:
    return [
        {
            "module": "ssl",
            "title": "SSL: certificate expired",
            "severity": "high",
            "confidence": 0.95,
            "data": {"host": "example.com"},
            "evidence": "notAfter < now",
        },
        {
            "module": "headers",
            "title": "Headers: strict-transport-security missing",
            "severity": "low",
            "confidence": 0.9,
            "data": {"header": "strict-transport-security"},
            "evidence": "strict-transport-security header absent",
        },
        {
            "module": "dns",
            "title": "DNS: no DMARC record",
            "severity": "low",
            "confidence": 0.8,
            "data": {"domain": "example.com"},
            "evidence": "no v=DMARC1 TXT record",
        },
        {
            "module": "news",
            "title": "News: timeline",
            "severity": "info",
            "confidence": 0.9,
            "data": {
                "articles": [
                    {
                        "title": "Story A",
                        "published": "2024-03-01T08:00:00+00:00",
                        "url": "https://p.example/a",
                        "source": "Publisher",
                    },
                    {
                        "title": "Story A",
                        "published": "2024-03-01T08:00:00+00:00",
                        "url": "https://p.example/a",
                        "source": "Publisher",
                    },
                ]
            },
            "evidence": "2 article(s)",
        },
    ]


def sample_model() -> Any:
    return build_report(
        sample_scan(),
        sample_target(),
        sample_findings(),
        generated_at=GENERATED_AT,
    )


def test_build_report_assembles_all_sections() -> None:
    model = sample_model()
    payload = model.to_dict()

    assert payload["scan"]["uuid"] == "u7"
    assert payload["scan"]["started_at"] == "2024-03-07T18:40:00"
    assert payload["scan"]["finished_at"] == "2024-03-07T18:41:00"
    assert payload["target"] == {"value": "example.com", "type": "domain"}
    assert payload["app"]["name"] == "IntelXtract"
    assert len(payload["findings"]) == 4

    risk = payload["risk"]
    assert risk["rating"] == "high"  # 35 + 9 + 6 = 50
    assert risk["categories"]["TLS"]["score"] == 35.0

    assert payload["severity_counts"] == {
        "critical": 0,
        "high": 1,
        "medium": 0,
        "low": 2,
        "info": 1,
    }
    assert payload["module_counts"] == [
        {"module": "dns", "count": 1},
        {"module": "headers", "count": 1},
        {"module": "news", "count": 1},
        {"module": "ssl", "count": 1},
    ]
    assert payload["executive_summary"]
    assert payload["methodology"]
    assert payload["evidence_refs"][0]["module"] == "ssl"
    assert payload["evidence_refs"][0]["title"] == "SSL: certificate expired"
    assert all(
        item["module"] in {"news", "dns", "headers"}
        for item in payload["evidence_refs"][1:]
    )


def test_build_report_timeline_sorted_and_deduped() -> None:
    events = sample_model().timeline
    assert [item["label"] for item in events].count("Story A") == 1
    assert [item["label"] for item in events] == [
        "Story A",
        "scan started",
        "scan finished",
    ]


def test_build_report_recomputes_correlation() -> None:
    correlation = sample_model().correlation
    assert correlation is not None
    kinds = {entity["kind"] for entity in correlation["entities"]}
    assert {"domain", "organization"} <= kinds
    values = {entity["value"] for entity in correlation["entities"]}
    assert "example.com" in values
    assert "p.example" in values


def test_build_report_without_findings() -> None:
    model = build_report(
        sample_scan(),
        sample_target(),
        [],
        generated_at=GENERATED_AT,
    )
    risk = model.risk
    assert risk is not None
    assert risk["score"] == 0.0
    assert risk["rating"] == "low"
    assert model.executive_summary == [
        "No findings were collected against example.com."
    ]
    assert model.severity_counts["high"] == 0
    assert model.correlation is not None  # target entity seeded


def test_build_report_is_deterministic() -> None:
    assert sample_model().to_dict() == sample_model().to_dict()


def test_golden_json_snapshot() -> None:
    assert GOLDEN.exists(), "golden snapshot is missing — regenerate with FAILURE dump"
    assert json.loads(json.dumps(sample_model().to_dict(), default=str)) == json.loads(
        GOLDEN.read_text(encoding="utf-8")
    )
