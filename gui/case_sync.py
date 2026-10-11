"""Synchronous case helpers for GUI pages (read + write).

Unlike :mod:`gui.db_sync` (read-only), the Cases page must create cases,
add notes, and attach scans. Writes use a short-lived read-write sqlite
connection on the Qt main thread; they are small and quick by design.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from database.repositories import utc_now


def _connect(db_path: str, *, write: bool = False) -> sqlite3.Connection | None:
    """Open a sqlite connection; ``None`` when a read target is missing."""
    if db_path == ":memory:":
        return None
    path = Path(db_path).expanduser()
    if write:
        conn = sqlite3.connect(path, timeout=2.0)
        conn.execute("PRAGMA foreign_keys = ON")
    else:
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
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def list_cases(db_path: str) -> list[dict[str, Any]]:
    """Cases with note/evidence counts, newest first."""
    return _fetchall(
        db_path,
        "SELECT cases.*,"
        " (SELECT COUNT(*) FROM case_notes n WHERE n.case_id = cases.id)"
        "   AS note_count,"
        " (SELECT COUNT(*) FROM case_evidence e WHERE e.case_id = cases.id)"
        "   AS evidence_count"
        " FROM cases ORDER BY cases.id DESC",
    )


def list_notes(db_path: str, case_id: int) -> list[dict[str, Any]]:
    """Notes for a case in insertion order."""
    return _fetchall(
        db_path,
        "SELECT * FROM case_notes WHERE case_id = ? ORDER BY id",
        (case_id,),
    )


def list_evidence(db_path: str, case_id: int) -> list[dict[str, Any]]:
    """Evidence rows for a case in insertion order."""
    return _fetchall(
        db_path,
        "SELECT * FROM case_evidence WHERE case_id = ? ORDER BY id",
        (case_id,),
    )


def case_findings(db_path: str, case_id: int) -> list[dict[str, Any]]:
    """Combined, de-duplicated findings across a case's evidence."""
    return _fetchall(
        db_path,
        "SELECT DISTINCT findings.* FROM findings"
        " JOIN case_evidence e ON findings.scan_id = e.scan_id"
        " WHERE e.case_id = ?"
        " UNION"
        " SELECT findings.* FROM findings"
        " JOIN case_evidence e ON findings.id = e.finding_id"
        " WHERE e.case_id = ?"
        " ORDER BY id",
        (case_id, case_id),
    )


def create_case(db_path: str, name: str, description: str = "") -> int:
    """Create a case; raises ``ValueError`` for blank/duplicate names."""
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("case name must not be empty")
    conn = _connect(db_path, write=True)
    if conn is None:
        raise ValueError("no database available")
    try:
        now = utc_now()
        try:
            cursor = conn.execute(
                "INSERT INTO cases (name, description, status, created_at,"
                " updated_at) VALUES (?, ?, 'open', ?, ?)",
                (cleaned, description.strip(), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"case already exists: {cleaned}") from exc
        conn.commit()
        return int(cursor.lastrowid or 0)
    finally:
        conn.close()


def add_note(db_path: str, case_id: int, body: str) -> int:
    """Append a note to a case; raises ``ValueError`` for blank bodies."""
    cleaned = body.strip()
    if not cleaned:
        raise ValueError("note body must not be empty")
    conn = _connect(db_path, write=True)
    if conn is None:
        raise ValueError("no database available")
    try:
        cursor = conn.execute(
            "INSERT INTO case_notes (case_id, body, created_at) VALUES (?, ?, ?)",
            (case_id, cleaned, utc_now()),
        )
        conn.execute(
            "UPDATE cases SET updated_at = ? WHERE id = ?", (utc_now(), case_id)
        )
        conn.commit()
        return int(cursor.lastrowid or 0)
    finally:
        conn.close()


def attach_scan(db_path: str, case_id: int, scan_id: int, label: str = "") -> int:
    """Attach a scan to a case as evidence."""
    conn = _connect(db_path, write=True)
    if conn is None:
        raise ValueError("no database available")
    try:
        now = utc_now()
        cursor = conn.execute(
            "INSERT INTO case_evidence (case_id, scan_id, finding_id, kind, label,"
            " detail, created_at) VALUES (?, ?, NULL, 'scan', ?, '', ?)",
            (case_id, scan_id, label.strip(), now),
        )
        conn.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now, case_id))
        conn.commit()
        return int(cursor.lastrowid or 0)
    finally:
        conn.close()
