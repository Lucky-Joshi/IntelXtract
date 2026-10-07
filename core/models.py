"""Normalized data models for the Phase 7 module system.

Modules return :class:`ModuleResult`; the normalizer
(:func:`parse_findings`) turns raw output into :class:`Finding` records that
are deduplicated by a stable content hash before they reach the engine, GUI,
and database layers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.constants import Severity
from core.exceptions import ValidationError

DEFAULT_CONFIDENCE = 0.5


def utc_now_iso() -> str:
    """Current UTC timestamp in the ISO-8601 format used across the app."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class Finding:
    """A normalized, deduplicatable piece of intelligence.

    ``content_hash`` is the dedupe key: a stable SHA-256 over the module,
    title, severity, evidence, and a canonical rendering of ``data``.  It is
    computed automatically when left empty.
    """

    module: str
    title: str
    data: dict[str, Any] = field(default_factory=dict)
    severity: Severity = Severity.INFO
    confidence: float = DEFAULT_CONFIDENCE
    evidence: str = ""
    collected_at: str = field(default_factory=utc_now_iso)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValidationError(
                f"confidence must be within 0..1, got {self.confidence!r}"
            )
        if self.module is None or not str(self.module).strip():
            raise ValidationError("finding requires a non-empty module name")
        if self.title is None or not str(self.title).strip():
            raise ValidationError("finding requires a non-empty title")
        if not self.content_hash:
            self.content_hash = content_hash(self)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation consumed by engine and DB."""
        return {
            "module": self.module,
            "title": self.title,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "data": self.data,
            "evidence": self.evidence,
            "collected_at": self.collected_at,
            "content_hash": self.content_hash,
        }


def content_hash(finding: Finding) -> str:
    """Stable SHA-256 identity of a finding (order-insensitive)."""
    payload = json.dumps(
        {
            "module": finding.module,
            "title": finding.title,
            "severity": finding.severity.value,
            "data": finding.data,
            "evidence": finding.evidence,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_finding(
    module: str,
    title: str,
    data: Mapping[str, Any] | None = None,
    *,
    severity: Severity | str = Severity.INFO,
    confidence: float = DEFAULT_CONFIDENCE,
    evidence: str = "",
    collected_at: str | None = None,
) -> Finding:
    """Build a :class:`Finding` with friendly defaults."""
    return Finding(
        module=module,
        title=title,
        data=dict(data or {}),
        severity=Severity(severity),
        confidence=confidence,
        evidence=evidence,
        collected_at=collected_at or utc_now_iso(),
    )


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """Remove duplicate findings by content hash, preserving order."""
    seen: set[str] = set()
    unique: list[Finding] = []
    for finding in findings:
        digest = finding.content_hash or content_hash(finding)
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(finding)
    return unique


def parse_findings(
    module: str,
    raw: Any,
    *,
    severity: Severity | str | None = None,
    confidence: float | None = None,
    evidence: str | None = None,
) -> list[Finding]:
    """Normalize raw module output into deduplicated findings.

    Accepts a single mapping/string (one finding) or a sequence of them, or a
    mapping wrapping them under ``findings``/``records``.  ``severity`` and
    ``confidence`` act as fallbacks for any item that omits them.
    """
    items: list[Mapping[str, Any]] = []
    if isinstance(raw, Mapping):
        wrapped = raw.get("findings") or raw.get("records")
        items = list(wrapped) if isinstance(wrapped, Sequence) else [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        items = [item for item in raw if isinstance(item, Mapping)]
    elif raw is not None:
        items = [{"title": str(raw), "data": {}}]

    findings: list[Finding] = []
    for item in items:
        title = item.get("title")
        if title is None:
            continue
        findings.append(
            make_finding(
                module,
                str(title),
                item.get("data"),
                severity=item.get("severity") or severity or Severity.INFO,
                confidence=item.get("confidence") or confidence or DEFAULT_CONFIDENCE,
                evidence=str(item.get("evidence") or evidence or ""),
            )
        )
    return dedupe(findings)


@dataclass(frozen=True, slots=True)
class ModuleResult:
    """Structured output of one ``BaseModule.run`` invocation.

    ``findings`` carry the normalized, deduplicated intelligence; ``data``
    holds any auxiliary/structural output the module wants to keep.
    """

    data: dict[str, Any] = field(default_factory=dict)
    findings: Sequence[Finding] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation for engine run records."""
        return {
            "data": self.data,
            "findings": [finding.to_dict() for finding in self.findings],
            "meta": self.meta,
        }
