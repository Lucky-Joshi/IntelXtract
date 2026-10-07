"""Typed repository layer — the only place SQL queries live besides migrations.

Rows are returned as frozen dataclasses; JSON columns are parsed on read.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from core.engine import ScanResult
from core.exceptions import DatabaseError
from database.connection import Database


def utc_now() -> str:
    """Current UTC time as ISO-8601."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _cursor_id(cursor: aiosqlite.Cursor) -> int:
    """Return the row id of a completed INSERT."""
    if cursor.lastrowid is None:
        raise DatabaseError("insert did not produce a row id")
    return int(cursor.lastrowid)


def epoch_to_iso(epoch: float | None) -> str | None:
    """Convert a POSIX timestamp to ISO-8601 UTC."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat(timespec="seconds")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(text: Any, default: Any) -> Any:
    try:
        return json.loads(str(text))
    except (json.JSONDecodeError, TypeError):
        return default


@dataclass(frozen=True, slots=True)
class TargetRecord:
    """A classified scan target."""

    id: int
    value: str
    type: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ScanRecord:
    """A persisted scan."""

    id: int
    target_id: int
    uuid: str
    mode: str
    status: str
    started_at: str
    finished_at: str | None
    duration: float
    error: str | None
    runs: list[dict[str, Any]]
    created_at: str


@dataclass(frozen=True, slots=True)
class FindingRecord:
    """A persisted finding."""

    id: int
    scan_id: int
    module: str
    title: str
    severity: str | None
    confidence: float | None
    data: dict[str, Any]
    evidence: str
    content_hash: str | None
    collected_at: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ReportRecord:
    """A generated report file registered in the database."""

    id: int
    scan_id: int
    path: str
    format: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PluginRecord:
    """Discovered plugin metadata."""

    id: int
    name: str
    version: str
    api_version: int
    enabled: bool
    description: str
    source: str
    error: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """API key metadata (never includes the secret itself)."""

    id: int
    provider: str
    hint: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class LogRecord:
    """A persisted log/audit event."""

    id: int
    level: str
    message: str
    source: str
    context: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    """A history event for a target."""

    id: int
    target_id: int
    scan_id: int | None
    event_type: str
    payload: dict[str, Any]
    created_at: str


def _target_row(row: sqlite3.Row) -> TargetRecord:
    return TargetRecord(
        id=int(row["id"]),
        value=str(row["value"]),
        type=str(row["type"]),
        created_at=str(row["created_at"]),
    )


def _scan_row(row: sqlite3.Row) -> ScanRecord:
    return ScanRecord(
        id=int(row["id"]),
        target_id=int(row["target_id"]),
        uuid=str(row["uuid"]),
        mode=str(row["mode"]),
        status=str(row["status"]),
        started_at=str(row["started_at"]),
        finished_at=row["finished_at"],
        duration=float(row["duration"]),
        error=row["error"],
        runs=list(_loads(row["runs_json"], [])),
        created_at=str(row["created_at"]),
    )


def _finding_row(row: sqlite3.Row) -> FindingRecord:
    return FindingRecord(
        id=int(row["id"]),
        scan_id=int(row["scan_id"]),
        module=str(row["module"]),
        title=str(row["title"]),
        severity=row["severity"],
        confidence=row["confidence"],
        data=dict(_loads(row["data"], {})),
        evidence=str(row["evidence"]),
        content_hash=row["content_hash"],
        collected_at=row["collected_at"],
        created_at=str(row["created_at"]),
    )


def _report_row(row: sqlite3.Row) -> ReportRecord:
    return ReportRecord(
        id=int(row["id"]),
        scan_id=int(row["scan_id"]),
        path=str(row["path"]),
        format=str(row["format"]),
        created_at=str(row["created_at"]),
    )


def _plugin_row(row: sqlite3.Row) -> PluginRecord:
    return PluginRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        version=str(row["version"]),
        api_version=int(row["api_version"]),
        enabled=bool(row["enabled"]),
        description=str(row["description"]),
        source=str(row["source"]),
        error=row["error"],
        updated_at=str(row["updated_at"]),
    )


def _api_key_row(row: sqlite3.Row) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=int(row["id"]),
        provider=str(row["provider"]),
        hint=str(row["hint"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _log_row(row: sqlite3.Row) -> LogRecord:
    return LogRecord(
        id=int(row["id"]),
        level=str(row["level"]),
        message=str(row["message"]),
        source=str(row["source"]),
        context=dict(_loads(row["context"], {})),
        created_at=str(row["created_at"]),
    )


def _history_row(row: sqlite3.Row) -> HistoryRecord:
    return HistoryRecord(
        id=int(row["id"]),
        target_id=int(row["target_id"]),
        scan_id=row["scan_id"],
        event_type=str(row["event_type"]),
        payload=dict(_loads(row["payload"], {})),
        created_at=str(row["created_at"]),
    )


class TargetRepository:
    """CRUD for classified targets."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_or_create(self, value: str, type_: str) -> TargetRecord:
        """Return the target row, creating it when first seen."""
        existing = await self._db.fetchone(
            "SELECT * FROM targets WHERE value = ? AND type = ?", (value, type_)
        )
        if existing is not None:
            return _target_row(existing)
        cursor = await self._db.execute(
            "INSERT INTO targets (value, type, created_at) VALUES (?, ?, ?)",
            (value, type_, utc_now()),
        )
        created = await self._db.fetchone(
            "SELECT * FROM targets WHERE id = ?", (_cursor_id(cursor),)
        )
        if created is None:
            raise DatabaseError("target insert did not produce a row")
        return _target_row(created)

    async def get(self, target_id: int) -> TargetRecord | None:
        """Fetch one target by id."""
        row = await self._db.fetchone(
            "SELECT * FROM targets WHERE id = ?", (target_id,)
        )
        return _target_row(row) if row is not None else None

    async def list(self) -> list[TargetRecord]:
        """All targets ordered by first appearance."""
        rows = await self._db.fetchall("SELECT * FROM targets ORDER BY id")
        return [_target_row(r) for r in rows]


class ScanRepository:
    """CRUD for scans."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        target_id: int,
        uuid: str,
        mode: str,
        status: str,
        started_at: str,
        duration: float = 0.0,
        finished_at: str | None = None,
        error: str | None = None,
        runs: Sequence[dict[str, Any]] = (),
    ) -> ScanRecord:
        """Insert a scan row and return it."""
        cursor = await self._db.execute(
            "INSERT INTO scans (target_id, uuid, mode, status, started_at,"
            " finished_at, duration, error, runs_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                target_id,
                uuid,
                mode,
                status,
                started_at,
                finished_at,
                duration,
                error,
                _dumps(list(runs)),
                utc_now(),
            ),
        )
        record = await self.get(_cursor_id(cursor))
        if record is None:
            raise DatabaseError("scan insert did not produce a row")
        return record

    async def create_for_result(self, target_id: int, result: ScanResult) -> ScanRecord:
        """Persist a completed engine :class:`ScanResult`."""
        return await self.create(
            target_id=target_id,
            uuid=result.scan_id,
            mode=result.mode.value,
            status=result.status.value,
            started_at=epoch_to_iso(result.started_at) or utc_now(),
            finished_at=epoch_to_iso(result.finished_at),
            duration=result.duration,
            error=result.error,
            runs=[run.to_dict() for run in result.runs],
        )

    async def get(self, scan_id: int) -> ScanRecord | None:
        """Fetch one scan by primary key."""
        row = await self._db.fetchone("SELECT * FROM scans WHERE id = ?", (scan_id,))
        return _scan_row(row) if row is not None else None

    async def get_by_uuid(self, uuid: str) -> ScanRecord | None:
        """Fetch one scan by engine uuid."""
        row = await self._db.fetchone("SELECT * FROM scans WHERE uuid = ?", (uuid,))
        return _scan_row(row) if row is not None else None

    async def list(
        self,
        *,
        limit: int = 50,
        target_id: int | None = None,
        status: str | None = None,
    ) -> list[ScanRecord]:
        """Recent scans, optionally filtered by target and/or status."""
        sql = "SELECT * FROM scans WHERE 1=1"
        params: list[Any] = []
        if target_id is not None:
            sql += " AND target_id = ?"
            params.append(target_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = await self._db.fetchall(sql, params)
        return [_scan_row(r) for r in rows]

    async def list_detailed(
        self,
        *,
        limit: int = 50,
        target_value: str | None = None,
        status: str | None = None,
    ) -> Sequence[tuple[ScanRecord, TargetRecord]]:
        """Recent scans joined with their target rows (newest first)."""
        sql = (
            "SELECT scans.*, targets.value AS target_value,"
            " targets.type AS target_type, targets.created_at AS target_created"
            " FROM scans JOIN targets ON targets.id = scans.target_id"
            " WHERE 1=1"
        )
        params: list[Any] = []
        if target_value is not None:
            sql += " AND targets.value = ?"
            params.append(target_value)
        if status is not None:
            sql += " AND scans.status = ?"
            params.append(status)
        sql += " ORDER BY scans.id DESC LIMIT ?"
        params.append(limit)
        rows = await self._db.fetchall(sql, params)
        joined: list[tuple[ScanRecord, TargetRecord]] = []
        for row in rows:
            joined.append(
                (
                    _scan_row(row),
                    TargetRecord(
                        id=int(row["target_id"]),
                        value=str(row["target_value"]),
                        type=str(row["target_type"]),
                        created_at=str(row["target_created"]),
                    ),
                )
            )
        return joined

    async def latest_for_target(self, target_id: int) -> ScanRecord | None:
        """Most recent scan for a target."""
        row = await self._db.fetchone(
            "SELECT * FROM scans WHERE target_id = ? ORDER BY id DESC LIMIT 1",
            (target_id,),
        )
        return _scan_row(row) if row is not None else None

    async def stats(self) -> dict[str, int]:
        """Scan counts grouped by status."""
        rows = await self._db.fetchall(
            "SELECT status, COUNT(*) AS n FROM scans GROUP BY status"
        )
        return {str(r["status"]): int(r["n"]) for r in rows}


class FindingRepository:
    """CRUD for findings."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def bulk_create(
        self, scan_id: int, findings: Sequence[dict[str, Any]]
    ) -> int:
        """Insert findings for a scan; returns how many were written.

        Each item requires ``module`` and ``data``; optional ``severity``,
        ``confidence``, ``title``, ``evidence``, ``content_hash``, and
        ``collected_at`` are stored as-is.
        """
        if not findings:
            return 0
        now = utc_now()
        rows = [
            (
                scan_id,
                str(item["module"]),
                str(item.get("title") or ""),
                item.get("severity"),
                item.get("confidence"),
                _dumps(item.get("data", {})),
                str(item.get("evidence") or ""),
                item.get("content_hash"),
                item.get("collected_at") or now,
                now,
            )
            for item in findings
        ]
        await self._db.executemany(
            "INSERT INTO findings (scan_id, module, title, severity, confidence,"
            " data, evidence, content_hash, collected_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        return len(rows)

    async def list_for_scan(self, scan_id: int) -> list[FindingRecord]:
        """All findings for a scan in insertion order."""
        rows = await self._db.fetchall(
            "SELECT * FROM findings WHERE scan_id = ? ORDER BY id", (scan_id,)
        )
        return [_finding_row(r) for r in rows]

    async def count_for_scan(self, scan_id: int) -> int:
        """Number of findings stored for a scan."""
        row = await self._db.fetchone(
            "SELECT COUNT(*) AS n FROM findings WHERE scan_id = ?", (scan_id,)
        )
        return int(row["n"]) if row is not None else 0


class ReportRepository:
    """CRUD for generated reports."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, scan_id: int, path: str, format: str) -> ReportRecord:
        """Register a report file for a scan."""
        cursor = await self._db.execute(
            "INSERT INTO reports (scan_id, path, format, created_at)"
            " VALUES (?, ?, ?, ?)",
            (scan_id, path, format, utc_now()),
        )
        row = await self._db.fetchone(
            "SELECT * FROM reports WHERE id = ?", (_cursor_id(cursor),)
        )
        if row is None:
            raise DatabaseError("report insert did not produce a row")
        return _report_row(row)

    async def list_for_scan(self, scan_id: int) -> list[ReportRecord]:
        """Reports generated for a scan."""
        rows = await self._db.fetchall(
            "SELECT * FROM reports WHERE scan_id = ? ORDER BY id", (scan_id,)
        )
        return [_report_row(r) for r in rows]


class PluginRepository:
    """Persisted plugin metadata and enable/disable state."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def sync(
        self,
        *,
        name: str,
        version: str,
        api_version: int,
        source: str,
        description: str = "",
        error: str | None = None,
        enabled: bool = True,
    ) -> None:
        """Insert or refresh a plugin; an existing ``enabled`` flag is kept."""
        await self._db.execute(
            "INSERT INTO plugins (name, version, api_version, enabled,"
            " description, source, error, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET"
            " version = excluded.version,"
            " api_version = excluded.api_version,"
            " description = excluded.description,"
            " source = excluded.source,"
            " error = excluded.error,"
            " updated_at = excluded.updated_at",
            (
                name,
                version,
                api_version,
                int(enabled),
                description,
                source,
                error,
                utc_now(),
            ),
        )

    async def set_enabled(self, name: str, enabled: bool) -> None:
        """Persist a plugin toggle (raises when the plugin is unknown)."""
        cursor = await self._db.execute(
            "UPDATE plugins SET enabled = ?, updated_at = ? WHERE name = ?",
            (int(enabled), utc_now(), name),
        )
        if cursor.rowcount == 0:
            raise DatabaseError(f"unknown plugin: {name}")

    async def get(self, name: str) -> PluginRecord | None:
        """Fetch a plugin row by name."""
        row = await self._db.fetchone("SELECT * FROM plugins WHERE name = ?", (name,))
        return _plugin_row(row) if row is not None else None

    async def list(self) -> list[PluginRecord]:
        """All plugin rows ordered by name."""
        rows = await self._db.fetchall("SELECT * FROM plugins ORDER BY name")
        return [_plugin_row(r) for r in rows]


class ApiKeyRepository:
    """Encrypted-at-rest API key storage (ciphertext never enters records)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def set(self, provider: str, ciphertext: str, hint: str = "") -> None:
        """Create or replace a provider's stored secret."""
        now = utc_now()
        await self._db.execute(
            "INSERT INTO api_keys (provider, ciphertext, hint, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(provider) DO UPDATE SET"
            " ciphertext = excluded.ciphertext,"
            " hint = excluded.hint,"
            " updated_at = excluded.updated_at",
            (provider, ciphertext, hint, now, now),
        )

    async def get(self, provider: str) -> ApiKeyRecord | None:
        """Fetch key metadata (no secret) for a provider."""
        row = await self._db.fetchone(
            "SELECT * FROM api_keys WHERE provider = ?", (provider,)
        )
        return _api_key_row(row) if row is not None else None

    async def get_ciphertext(self, provider: str) -> str | None:
        """Fetch the stored ciphertext (decryption belongs to the vault)."""
        row = await self._db.fetchone(
            "SELECT ciphertext FROM api_keys WHERE provider = ?", (provider,)
        )
        return str(row["ciphertext"]) if row is not None else None

    async def delete(self, provider: str) -> bool:
        """Remove a provider's key; returns whether a row existed."""
        cursor = await self._db.execute(
            "DELETE FROM api_keys WHERE provider = ?", (provider,)
        )
        return cursor.rowcount > 0

    async def list(self) -> list[ApiKeyRecord]:
        """Metadata for every stored key, ordered by provider."""
        rows = await self._db.fetchall("SELECT * FROM api_keys ORDER BY provider")
        return [_api_key_row(r) for r in rows]


class LogRepository:
    """Persisted log/audit events."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        level: str,
        message: str,
        *,
        source: str = "",
        context: dict[str, Any] | None = None,
    ) -> LogRecord:
        """Append a log event."""
        cursor = await self._db.execute(
            "INSERT INTO logs (level, message, source, context, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (level, message, source, _dumps(context or {}), utc_now()),
        )
        row = await self._db.fetchone(
            "SELECT * FROM logs WHERE id = ?", (_cursor_id(cursor),)
        )
        if row is None:
            raise DatabaseError("log insert did not produce a row")
        return _log_row(row)

    async def recent(self, limit: int = 100) -> list[LogRecord]:
        """Newest-first log events."""
        rows = await self._db.fetchall(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [_log_row(r) for r in rows]


class HistoryRepository:
    """History events per target (change detection, milestones)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        target_id: int,
        event_type: str,
        payload: dict[str, Any],
        *,
        scan_id: int | None = None,
    ) -> HistoryRecord:
        """Append a history event for a target."""
        cursor = await self._db.execute(
            "INSERT INTO history (target_id, scan_id, event_type, payload,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            (target_id, scan_id, event_type, _dumps(payload), utc_now()),
        )
        row = await self._db.fetchone(
            "SELECT * FROM history WHERE id = ?", (_cursor_id(cursor),)
        )
        if row is None:
            raise DatabaseError("history insert did not produce a row")
        return _history_row(row)

    async def list_for_target(
        self, target_id: int, limit: int = 50
    ) -> list[HistoryRecord]:
        """Newest-first history events for a target."""
        rows = await self._db.fetchall(
            "SELECT * FROM history WHERE target_id = ? ORDER BY id DESC LIMIT ?",
            (target_id, limit),
        )
        return [_history_row(r) for r in rows]


class SettingRepository:
    """DB-backed runtime settings (JSON values)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str, default: Any = None) -> Any:
        """Read a JSON-encoded setting."""
        row = await self._db.fetchone(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        if row is None:
            return default
        return _loads(row["value"], default)

    async def set(self, key: str, value: Any) -> None:
        """Create or replace a JSON-encoded setting."""
        await self._db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at",
            (key, _dumps(value), utc_now()),
        )

    async def delete(self, key: str) -> bool:
        """Remove a setting; returns whether it existed."""
        cursor = await self._db.execute("DELETE FROM settings WHERE key = ?", (key,))
        return cursor.rowcount > 0

    async def all(self) -> dict[str, Any]:
        """Every setting as a key/decoded-value mapping."""
        rows = await self._db.fetchall("SELECT key, value FROM settings ORDER BY key")
        return {str(r["key"]): _loads(r["value"], None) for r in rows}


class Repositories:
    """Convenience bundle of every repository sharing one connection."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.targets = TargetRepository(db)
        self.scans = ScanRepository(db)
        self.findings = FindingRepository(db)
        self.reports = ReportRepository(db)
        self.plugins = PluginRepository(db)
        self.api_keys = ApiKeyRepository(db)
        self.logs = LogRepository(db)
        self.history = HistoryRepository(db)
        self.settings = SettingRepository(db)
