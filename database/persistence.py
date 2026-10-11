"""Persisting engine results and plugin metadata into the repository layer.

The engine never imports the database; it accepts a ``result_sink`` callable.
:func:`make_result_sink` adapts :class:`Database` to that seam.
"""

from __future__ import annotations

from typing import Any

from core.engine import ResultSink, ScanResult
from core.plugin_loader import PluginRegistry
from core.scheduling import diff_findings
from database.connection import Database
from database.repositories import (
    CaseRecord,
    FindingRecord,
    HistoryRecord,
    Repositories,
)


async def save_scan_result(db: Database, result: ScanResult) -> int:
    """Persist a completed scan and its findings; returns the scan id."""
    repos = Repositories(db)
    target = await repos.targets.get_or_create(result.target, result.target_type.value)
    scan = await repos.scans.create_for_result(target.id, result)
    await repos.findings.bulk_create(scan.id, result.findings)
    return scan.id


def _finding_mapping(finding: FindingRecord) -> dict[str, Any]:
    """Flatten a persisted finding into the mapping diff_findings expects."""
    return {
        "module": finding.module,
        "title": finding.title,
        "severity": finding.severity,
        "content_hash": finding.content_hash,
        "data": finding.data,
    }


async def record_scan_change(
    repos: Repositories,
    target_id: int,
    *,
    previous_scan_id: int | None,
    current_scan_id: int,
) -> HistoryRecord:
    """Write a ``history`` entry diffing two scans of the same target.

    The first scan for a target records a ``baseline`` event; later scans
    record a ``change`` event with added/removed/changed findings.
    """
    current = await repos.findings.list_for_scan(current_scan_id)
    if previous_scan_id is None or previous_scan_id == current_scan_id:
        return await repos.history.add(
            target_id,
            "baseline",
            {"scan_id": current_scan_id, "findings": len(current)},
            scan_id=current_scan_id,
        )
    previous = await repos.findings.list_for_scan(previous_scan_id)
    delta = diff_findings(
        [_finding_mapping(finding) for finding in previous],
        [_finding_mapping(finding) for finding in current],
    )
    payload = {
        "previous_scan_id": previous_scan_id,
        "current_scan_id": current_scan_id,
        **delta.to_payload(),
    }
    return await repos.history.add(
        target_id, "change", payload, scan_id=current_scan_id
    )


def _finding_dict(finding: FindingRecord) -> dict[str, Any]:
    """Shape a persisted finding for the report builder."""
    return {
        "id": finding.id,
        "module": finding.module,
        "title": finding.title,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "data": finding.data,
        "evidence": finding.evidence,
        "content_hash": finding.content_hash,
        "collected_at": finding.collected_at,
        "created_at": finding.created_at,
    }


async def collect_case_payload(repos: Repositories, case: CaseRecord) -> dict[str, Any]:
    """Assemble everything needed to render a case as a combined report.

    Findings from every attached scan plus directly attached findings are
    de-duplicated by id so overlapping evidence never double-counts.
    """
    evidence = await repos.cases.list_evidence(case.id)
    scan_ids = sorted({e.scan_id for e in evidence if e.scan_id is not None})
    finding_ids = sorted({e.finding_id for e in evidence if e.finding_id is not None})

    findings: list[dict[str, Any]] = []
    seen: set[int] = set()
    for scan_id in scan_ids:
        for finding in await repos.findings.list_for_scan(scan_id):
            if finding.id not in seen:
                seen.add(finding.id)
                findings.append(_finding_dict(finding))
    for finding_id in finding_ids:
        record = await repos.findings.get(finding_id)
        if record is not None and record.id not in seen:
            seen.add(record.id)
            findings.append(_finding_dict(record))

    return {
        "case": case,
        "scan": {
            "id": None,
            "uuid": f"case-{case.id}",
            "mode": "case",
            "status": case.status,
            "started_at": case.created_at,
            "finished_at": None,
            "duration": None,
            "error": None,
            "runs": [],
        },
        "target": {"value": case.name, "type": "case"},
        "findings": findings,
        "evidence": evidence,
        "scan_ids": scan_ids,
    }


def make_result_sink(db: Database) -> ResultSink:
    """Build the engine ``result_sink`` callable backed by ``db``."""

    async def sink(result: ScanResult) -> None:
        await save_scan_result(db, result)

    return sink


async def sync_plugins(db: Database, registry: PluginRegistry) -> int:
    """Upsert discovered plugin metadata; existing enable flags are kept.

    Returns the number of plugins written.
    """
    repos = Repositories(db)
    infos = registry.discover()
    for info in infos:
        await repos.plugins.sync(
            name=info.name,
            version=info.version,
            api_version=info.api_version,
            source=str(info.source),
            description=info.description,
            error=info.error,
            enabled=registry.is_enabled(info.name),
        )
    return len(infos)
