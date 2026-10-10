"""Phase 19 (S19.1): shared report content model.

``build_report`` assembles an :class:`ReportModel` from a scan row, its
target, and findings, re-deriving the Phase 16 correlation graph and Phase 17
risk score when they are not supplied. Every exporter consumes this model, so
JSON / HTML / CSV / Markdown / PDF stay byte-consistent.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from dataclasses import dataclass
from typing import Any

from core.constants import VERSION, TargetType
from core.correlation import build_graph
from core.risk import assess_risk
from reports.brand import brand_tokens

SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

METHODOLOGY = (
    "Passive reconnaissance only: DNS, RDAP/WHOIS, certificate transparency, "
    "and HTTP fingerprints gathered from public sources.",
    "Indicators originate from the configured module set and are de-duplicated "
    "by content hash before scoring.",
    "Risk scores are deterministic weights over concrete findings; every "
    "contributing rule is listed in the risk overview.",
)

# Columns shown as evidence references (module, title, evidence) in reports.
EVIDENCE_LIMIT = 6


def _iso(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        moment = _dt.datetime.fromtimestamp(float(value), tz=_dt.UTC).replace(
            tzinfo=None
        )
        return moment.isoformat()
    return str(value) if value else None


def _epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            moment = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.UTC)
        return moment.timestamp()
    return None


def _severity_rank(severity: Any) -> int:
    value = str(severity or "info")
    return (
        SEVERITY_ORDER.index(value) if value in SEVERITY_ORDER else len(SEVERITY_ORDER)
    )


def _normalize_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce the dict shape the model and risk rules expect."""
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        normalized.append(
            {
                "module": str(finding.get("module") or "unknown"),
                "title": str(finding.get("title") or ""),
                "severity": str(finding.get("severity") or "info"),
                "confidence": finding.get("confidence"),
                "data": finding.get("data", {}),
                "evidence": str(finding.get("evidence") or ""),
                "created_at": _iso(
                    finding.get("collected_at") or finding.get("created_at")
                ),
            }
        )
    return normalized


def _module_counts(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(finding["module"]) for finding in findings)
    return [
        {"module": module, "count": int(count)}
        for module, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _timeline(
    scan: dict[str, Any], findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    started = _epoch(scan.get("started_at"))
    finished = _epoch(scan.get("finished_at"))
    if started is not None:
        events.append({"ts": started, "kind": "scan", "label": "scan started"})
    if finished is not None:
        events.append({"ts": finished, "kind": "scan", "label": "scan finished"})
    seen: set[tuple[str, float, str]] = set()
    for finding in findings:
        if finding["module"] != "news" or not isinstance(finding["data"], dict):
            continue
        for article in finding["data"].get("articles") or []:
            if not isinstance(article, dict):
                continue
            published = _epoch(article.get("published"))
            if published is None:
                continue
            label = str(article.get("title") or "news item")
            key = ("news", published, label)
            if key in seen:
                continue
            seen.add(key)
            events.append({"ts": published, "kind": "news", "label": label})
    events.sort(key=lambda item: (item["ts"], item["kind"], item["label"]))
    return events


def _executive_summary(
    *,
    target: str,
    findings: list[dict[str, Any]],
    risk: dict[str, Any] | None,
) -> list[str]:
    if not findings:
        return [f"No findings were collected against {target}."]
    rating = str((risk or {}).get("rating") or "low").upper()
    score = float((risk or {}).get("score") or 0.0)
    lines = [
        f"{rating} overall risk ({score:.0f}/100) assessed for {target} "
        f"across {len(findings)} finding(s)."
    ]
    top = sorted(
        findings,
        key=lambda item: (
            _severity_rank(item["severity"]),
            item["module"],
            item["title"],
        ),
    )
    for finding in top[:3]:
        title = finding["title"] or f"{finding['module']} finding"
        lines.append(f"{finding['severity'].upper()} — {title} in {finding['module']}.")
    return lines


def _evidence_refs(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    ranked = sorted(
        findings,
        key=lambda item: (
            _severity_rank(item["severity"]),
            item["module"],
            item["title"],
        ),
    )
    refs: list[dict[str, str]] = []
    for finding in ranked[:EVIDENCE_LIMIT]:
        if finding["evidence"]:
            refs.append(
                {
                    "module": finding["module"],
                    "title": finding["title"],
                    "evidence": finding["evidence"],
                }
            )
    return refs


def _correlation_for(
    findings: list[dict[str, Any]], *, target: str, target_type: TargetType | None
) -> dict[str, Any] | None:
    if target_type is None:
        return None
    try:
        graph = build_graph(findings, target=target, target_type=target_type)
        return graph.to_dict() if graph is not None else None
    except Exception:
        return None


@dataclass
class ReportModel:
    """Everything a report renderer needs, in one serializable object."""

    generated_at: str
    app: dict[str, Any]
    scan: dict[str, Any]
    target: dict[str, Any] | None
    findings: list[dict[str, Any]]
    correlation: dict[str, Any] | None
    risk: dict[str, Any] | None
    severity_counts: dict[str, int]
    module_counts: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    executive_summary: list[str]
    evidence_refs: list[dict[str, str]]
    methodology: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "app": self.app,
            "scan": self.scan,
            "target": self.target,
            "findings": self.findings,
            "correlation": self.correlation,
            "risk": self.risk,
            "severity_counts": self.severity_counts,
            "module_counts": self.module_counts,
            "timeline": self.timeline,
            "executive_summary": self.executive_summary,
            "evidence_refs": self.evidence_refs,
            "methodology": self.methodology,
        }


def build_report(
    scan: dict[str, Any],
    target: dict[str, Any] | None,
    findings: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> ReportModel:
    """Assemble the shared report model from a scan, target, and findings.

    Correlation and risk are re-derived deterministically from the findings so
    reports work for persisted scans that predate Phase 16/17 storage.
    """
    normalized = _normalize_findings(findings)
    target_value = str((target or {}).get("value") or "")
    try:
        target_type: TargetType | None = (
            TargetType(str((target or {}).get("type")))
            if (target or {}).get("type")
            else None
        )
    except ValueError:
        target_type = None
    try:
        risk = assess_risk(normalized, target=target_value).to_dict()
    except Exception:
        risk = None
    correlation = _correlation_for(
        normalized, target=target_value, target_type=target_type
    )

    severity_counts = {
        level: sum(1 for item in normalized if item["severity"] == level)
        for level in SEVERITY_ORDER
    }

    now = generated_at or _dt.datetime.now().isoformat(timespec="seconds")
    return ReportModel(
        generated_at=now,
        app={
            "name": brand_tokens()["name"],
            "version": VERSION,
        },
        scan={
            "id": scan.get("id"),
            "uuid": scan.get("uuid"),
            "mode": scan.get("mode"),
            "status": scan.get("status"),
            "started_at": _iso(scan.get("started_at")),
            "finished_at": _iso(scan.get("finished_at")),
            "duration": scan.get("duration"),
            "error": scan.get("error"),
            "runs": scan.get("runs", []),
        },
        target=target,
        findings=normalized,
        correlation=correlation,
        risk=risk,
        severity_counts=severity_counts,
        module_counts=_module_counts(normalized),
        timeline=_timeline(scan, normalized),
        executive_summary=_executive_summary(
            target=target_value, findings=normalized, risk=risk
        ),
        evidence_refs=_evidence_refs(normalized),
        methodology=list(METHODOLOGY),
    )


__all__ = ["SEVERITY_ORDER", "ReportModel", "build_report"]
