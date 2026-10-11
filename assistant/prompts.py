"""Grounding prompt templates (Phase 23, S23.2).

Every template shares one guardrail system prompt that forbids fabricating
facts and requires the model to cite the evidence it used. Report content is
serialized as JSON so the model reasons over exactly what was collected.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from assistant.providers import ChatMessage
from reports.builder import ReportModel

SYSTEM_GUARDRAIL = (
    "You are the IntelXtract analysis assistant. You help a security analyst "
    "understand intelligence that IntelXtract already collected. "
    "Use ONLY the evidence supplied in the user message. "
    "Do not invent, guess, or embellish hosts, IPs, dates, CVEs, credentials, "
    "or vulnerabilities that are not present in the evidence. "
    "If the evidence is insufficient to answer, say so explicitly instead of "
    "speculating. Never claim that AI-generated text is a scan finding. "
    "Answer in concise Markdown and finish with a short 'Basis' list naming "
    "the evidence items you relied on."
)

_TASKS = {
    "summarize": (
        "Task: write a short executive summary of this scan for an analyst. "
        "State the overall risk, the most important findings, and anything "
        "that needs urgent attention."
    ),
    "explain": (
        "Task: explain the single finding below in plain language — what it "
        "means, why it matters, and how confident the analyst should be. "
        "Base every statement on the finding and any scan context provided."
    ),
    "compare": (
        "Task: compare the two scans of the same target. Describe what was "
        "added, removed, or changed between the earlier and later scan and "
        "what that shift likely means. Only reference differences present in "
        "the supplied evidence."
    ),
    "next_steps": (
        "Task: recommend concrete, defensive next steps for the analyst. "
        "Each step must be grounded in a supplied finding; do not invent "
        "assets, systems, or vulnerabilities."
    ),
}


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _findings(model: ReportModel) -> list[dict[str, Any]]:
    return [
        {
            "module": finding.get("module"),
            "title": finding.get("title"),
            "severity": finding.get("severity"),
            "confidence": finding.get("confidence"),
            "evidence": finding.get("evidence"),
            "data": finding.get("data"),
        }
        for finding in model.findings
    ]


def report_context(model: ReportModel) -> dict[str, Any]:
    """Compact, evidence-complete rendering of a report model."""
    return {
        "target": model.target,
        "scan": model.scan,
        "overall_risk": model.risk,
        "severity_counts": model.severity_counts,
        "module_counts": model.module_counts,
        "executive_summary": model.executive_summary,
        "correlation": model.correlation,
        "evidence_refs": model.evidence_refs,
        "findings": _findings(model),
        "timeline": model.timeline,
    }


def finding_dict(finding: Any) -> dict[str, Any]:
    """Normalize a persisted finding / mapping for a prompt."""
    if isinstance(finding, Mapping):
        source: Mapping[str, Any] = finding
    else:
        source = {
            key: getattr(finding, key, None)
            for key in ("module", "title", "severity", "confidence", "evidence", "data")
        }
    return {
        "module": source.get("module"),
        "title": source.get("title"),
        "severity": source.get("severity"),
        "confidence": source.get("confidence"),
        "evidence": source.get("evidence") or "",
        "data": source.get("data") or {},
    }


def _messages(task: str, user_block: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=f"{SYSTEM_GUARDRAIL}\n\n{_TASKS[task]}"),
        ChatMessage(role="user", content=user_block),
    ]


def summarize_messages(model: ReportModel) -> list[ChatMessage]:
    """Messages asking for an executive summary of a scan."""
    return _messages(
        "summarize", "Scan evidence (JSON):\n" + _json(report_context(model))
    )


def next_steps_messages(model: ReportModel) -> list[ChatMessage]:
    """Messages asking for grounded defensive next steps."""
    return _messages(
        "next_steps", "Scan evidence (JSON):\n" + _json(report_context(model))
    )


def explain_messages(
    finding: Any, model: ReportModel | None = None
) -> list[ChatMessage]:
    """Messages asking to explain one finding, optionally with scan context."""
    blocks = ["Finding (JSON):\n" + _json(finding_dict(finding))]
    if model is not None:
        blocks.append("Scan context (JSON):\n" + _json(report_context(model)))
    return _messages("explain", "\n\n".join(blocks))


def compare_messages(before: ReportModel, after: ReportModel) -> list[ChatMessage]:
    """Messages asking to compare an earlier and a later scan."""
    block = (
        "Earlier scan (JSON):\n"
        + _json(report_context(before))
        + "\n\nLater scan (JSON):\n"
        + _json(report_context(after))
    )
    return _messages("compare", block)


__all__ = [
    "SYSTEM_GUARDRAIL",
    "compare_messages",
    "explain_messages",
    "finding_dict",
    "next_steps_messages",
    "report_context",
    "summarize_messages",
]
