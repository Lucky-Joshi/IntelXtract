"""Phase 23, S23.2: grounded prompt template assembly."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from assistant.prompts import (
    SYSTEM_GUARDRAIL,
    compare_messages,
    explain_messages,
    finding_dict,
    next_steps_messages,
    report_context,
    summarize_messages,
)
from reports.builder import build_report


def _model() -> Any:
    return build_report(
        {
            "id": 1,
            "uuid": "u-1",
            "mode": "quick",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "duration": 1.0,
            "error": None,
            "runs": [],
        },
        {"value": "example.com", "type": "domain"},
        [
            {
                "module": "dns",
                "title": "Open resolver",
                "severity": "medium",
                "confidence": 0.8,
                "data": {"port": 53},
                "evidence": "ref=1",
            }
        ],
    )


def test_guardrail_forbids_invention() -> None:
    lowered = SYSTEM_GUARDRAIL.lower()
    assert "do not invent" in lowered
    assert "insufficient" in lowered
    assert "scan finding" in lowered


def test_summarize_message_shape() -> None:
    messages = summarize_messages(_model())
    assert [message.role for message in messages] == ["system", "user"]
    user = messages[1].content
    assert "Scan evidence" in user
    payload = json.loads(user.split("JSON):\n", 1)[1])
    assert payload["target"] == {"value": "example.com", "type": "domain"}
    assert payload["findings"][0]["title"] == "Open resolver"


def test_report_context_carries_raw_evidence() -> None:
    context = report_context(_model())
    assert context["evidence_refs"] == [
        {"module": "dns", "title": "Open resolver", "evidence": "ref=1"}
    ]
    assert context["findings"][0]["data"] == {"port": 53}


def test_next_steps_messages() -> None:
    messages = next_steps_messages(_model())
    assert messages[0].role == "system"
    assert "recommend concrete" in messages[0].content


def test_explain_messages_with_and_without_context() -> None:
    finding = {
        "module": "dns",
        "title": "Open resolver",
        "severity": "medium",
        "confidence": 0.8,
        "evidence": "ref=1",
        "data": {},
    }
    isolated = explain_messages(finding)
    assert "Finding" in isolated[1].content
    assert "Scan context" not in isolated[1].content
    with_scene = explain_messages(finding, _model())
    assert "Scan context" in with_scene[1].content


def test_compare_messages_name_both_scans() -> None:
    messages = compare_messages(_model(), _model())
    assert "Earlier scan" in messages[1].content
    assert "Later scan" in messages[1].content


def test_finding_dict_normalizes_object_and_mapping() -> None:
    obj = SimpleNamespace(
        module="dns",
        title="t",
        severity="high",
        confidence=0.9,
        evidence="e",
        data={"a": 1},
    )
    assert finding_dict(obj)["severity"] == "high"
    raw = {"module": "dns", "title": "t"}
    assert finding_dict(raw)["evidence"] == ""
    assert finding_dict(raw)["data"] == {}
