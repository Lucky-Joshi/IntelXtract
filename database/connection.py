"""Async SQLite connection layer (schema and repositories arrive in Phase 3)."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from core.config import Config
from core.exceptions import DatabaseError

Params = Sequence[Any] | dict[str, Any]


def _resolve_path(raw: str) -> str:
    """Expand ``~`` in a database path (sync helper for async callers)."""
    if raw == ":memory:":
        return raw
    return str(Path(raw).expanduser())


class Database:
    """Thin async wrapper over a single SQLite connection."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def path(self) -> str:
        """Filesystem path (or ``:memory:``) of the database."""
        return self._path

    @property
    def conn(self) -> aiosqlite.Connection:
        """The underlying connection; raises if not connected."""
        if self._conn is None:
            raise DatabaseError("database is not connected")
        return self._conn

    def _prepare_parent(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> Database:
        """Open the connection and apply baseline pragmas."""
        if self._conn is not None:
            return self
        if self._path != ":memory:":
            await asyncio.to_thread(self._prepare_parent)
        try:
            self._conn = await aiosqlite.connect(self._path)
        except sqlite3.Error as exc:
            raise DatabaseError(f"cannot open database {self._path}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        if self._path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode = WAL")
        return self

    async def close(self) -> None:
        """Close the connection if open."""
        if self._conn is not None:
            conn, self._conn = self._conn, None
            try:
                await conn.close()
            except sqlite3.Error as exc:
                raise DatabaseError(f"error closing database: {exc}") from exc

    async def execute(self, sql: str, params: Params = ()) -> aiosqlite.Cursor:
        """Execute a statement and return its cursor."""
        try:
            return await self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(f"query failed: {exc}") from exc

    async def executemany(self, sql: str, seq: Sequence[Params]) -> aiosqlite.Cursor:
        """Execute a statement against a sequence of parameter sets."""
        try:
            return await self.conn.executemany(sql, seq)
        except sqlite3.Error as exc:
            raise DatabaseError(f"query failed: {exc}") from exc

    async def fetchone(self, sql: str, params: Params = ()) -> sqlite3.Row | None:
        """Return the first row or ``None``."""
        cursor = await self.execute(sql, params)
        row: sqlite3.Row | None = await cursor.fetchone()
        return row

    async def fetchall(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        """Return all rows."""
        cursor = await self.execute(sql, params)
        rows: list[sqlite3.Row] = list(await cursor.fetchall())
        return rows

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        """Context manager wrapping BEGIN/COMMIT/ROLLBACK."""
        try:
            await self.execute("BEGIN")
        except DatabaseError as exc:
            raise DatabaseError(f"cannot begin transaction: {exc}") from exc
        try:
            yield self
        except BaseException as exc:
            await self.conn.rollback()
            if isinstance(exc, DatabaseError):
                raise
            raise DatabaseError(f"transaction rolled back: {exc}") from exc
        else:
            try:
                await self.conn.commit()
            except sqlite3.Error as exc:
                raise DatabaseError(f"cannot commit transaction: {exc}") from exc


async def open_database(config: Config) -> Database:
    """Open the database configured at ``paths.db_path``."""
    path = _resolve_path(str(config.get("paths.db_path", ":memory:")))
    db = Database(path)
    await db.connect()
    return db
