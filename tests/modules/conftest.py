"""Shared fixtures for module and engine tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from database.connection import Database


@pytest.fixture(autouse=True)
async def close_engine_databases(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[None]:
    """Close databases opened by engine test helpers for persistence.

    The per-module ``_engine(persist=True)`` helpers wire a ``result_sink``
    backed by a real :class:`~database.connection.Database` but return before
    it can be closed. The connection's ``aiosqlite`` worker thread then
    outlives the test's event loop and raises ``RuntimeError: Event loop is
    closed`` while delivering a late result. Track every connection opened
    during the test and close it before the loop tears down.
    """
    opened: list[Database] = []
    original_connect = Database.connect

    async def tracking_connect(self: Database) -> Database:
        db = await original_connect(self)
        opened.append(db)
        return db

    monkeypatch.setattr(Database, "connect", tracking_connect)
    yield
    for db in opened:
        await db.close()
