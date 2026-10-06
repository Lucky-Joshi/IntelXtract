"""Synchronous, read-only database helpers for GUI pages.

Pages run on the Qt main thread; these helpers open short-lived read-only
sqlite connections so the UI never blocks on the asyncio worker.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def _connect(db_path: str) -> sqlite3.Connection | None:
    """Open a read-only connection; ``None`` when the file is missing."""
    if db_path == ":memory:":
        return None
    path = Path(db_path).expanduser()
    if not path.is_file():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def _fetchall(
    db_path: str, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def scan_stats(db_path: str) -> dict[str, int]:
    """Scan counts grouped by status."""
    rows = _fetchall(db_path, "SELECT status, COUNT(*) AS n FROM scans GROUP BY status")
    return {str(row["status"]): int(row["n"]) for row in rows}


def recent_scans(
    db_path: str,
    *,
    limit: int = 20,
    target: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Recent scans joined with targets, newest first."""
    sql = (
        "SELECT scans.id, scans.uuid, scans.mode, scans.status, scans.started_at,"
        " scans.duration, scans.error, scans.runs_json,"
        " targets.value AS target, targets.type AS type, scans.target_id"
        " FROM scans JOIN targets ON targets.id = scans.target_id WHERE 1=1"
    )
    params: list[Any] = []
    if target:
        sql += " AND targets.value LIKE ?"
        params.append(f"%{target}%")
    if status:
        sql += " AND scans.status = ?"
        params.append(status)
    sql += " ORDER BY scans.id DESC LIMIT ?"
    params.append(limit)
    return _fetchall(db_path, sql, tuple(params))


def get_scan(db_path: str, scan_id: int) -> dict[str, Any] | None:
    """One scan row by primary key."""
    rows = _fetchall(db_path, "SELECT * FROM scans WHERE id = ?", (scan_id,))
    return rows[0] if rows else None


def get_target(db_path: str, target_id: int) -> dict[str, Any] | None:
    """One target row by primary key."""
    rows = _fetchall(db_path, "SELECT * FROM targets WHERE id = ?", (target_id,))
    return rows[0] if rows else None


def list_findings(db_path: str, scan_id: int) -> list[dict[str, Any]]:
    """Persisted findings for a scan."""
    return _fetchall(
        db_path,
        "SELECT * FROM findings WHERE scan_id = ? ORDER BY id",
        (scan_id,),
    )


def list_reports(db_path: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Generated report files, newest first."""
    return _fetchall(
        db_path,
        "SELECT * FROM reports ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def build_scan_payload(db_path: str, scan_id: int) -> dict[str, Any] | None:
    """Assemble a results-page payload for a persisted scan."""
    scan = get_scan(db_path, scan_id)
    if scan is None:
        return None
    target = get_target(db_path, int(scan["target_id"]))
    runs: list[Any] = []
    raw_runs = scan.get("runs_json")
    if raw_runs:
        try:
            parsed = json.loads(str(raw_runs))
            if isinstance(parsed, list):
                runs = parsed
        except (json.JSONDecodeError, TypeError):
            runs = []
    return {
        "scan": {
            "id": scan["id"],
            "uuid": scan["uuid"],
            "mode": scan["mode"],
            "status": scan["status"],
            "started_at": scan["started_at"],
            "finished_at": scan["finished_at"],
            "duration": scan["duration"],
            "error": scan["error"],
            "runs": runs,
        },
        "target": (
            {"value": target["value"], "type": target["type"]} if target else None
        ),
        "findings": list_findings(db_path, scan_id),
    }
