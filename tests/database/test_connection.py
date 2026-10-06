"""Database connection layer tests."""

from pathlib import Path

import pytest

from core.config import Config
from core.exceptions import DatabaseError
from database.connection import Database, open_database


async def test_connect_execute_fetch_roundtrip() -> None:
    db = Database(":memory:")
    await db.connect()
    await db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    await db.execute("INSERT INTO items (name) VALUES (?)", ("alpha",))
    await db.executemany(
        "INSERT INTO items (name) VALUES (?)",
        [("beta",), ("gamma",)],
    )
    row = await db.fetchone("SELECT name FROM items WHERE id = ?", (1,))
    assert row is not None
    assert row["name"] == "alpha"
    rows = await db.fetchall("SELECT name FROM items ORDER BY id")
    assert [r["name"] for r in rows] == ["alpha", "beta", "gamma"]
    await db.close()


async def test_fetchone_returns_none_when_empty() -> None:
    db = Database(":memory:")
    await db.connect()
    await db.execute("CREATE TABLE empty (id INTEGER)")
    assert await db.fetchone("SELECT * FROM empty") is None
    await db.close()


async def test_connect_is_idempotent() -> None:
    db = Database(":memory:")
    first = await db.connect()
    second = await db.connect()
    assert first is second
    await db.close()


async def test_use_after_close_raises() -> None:
    db = Database(":memory:")
    await db.connect()
    await db.close()
    with pytest.raises(DatabaseError):
        await db.execute("SELECT 1")


async def test_invalid_sql_raises_database_error() -> None:
    db = Database(":memory:")
    await db.connect()
    with pytest.raises(DatabaseError):
        await db.execute("SELECT * FROM does_not_exist")
    await db.close()


async def test_foreign_keys_enforced() -> None:
    db = Database(":memory:")
    await db.connect()
    await db.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    await db.execute(
        "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER "
        "REFERENCES parent(id))"
    )
    with pytest.raises(DatabaseError):
        await db.execute("INSERT INTO child (parent_id) VALUES (999)")
    await db.close()


async def test_transaction_commit() -> None:
    db = Database(":memory:")
    await db.connect()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    async with db.transaction():
        await db.execute("INSERT INTO t (id) VALUES (1)")
        await db.execute("INSERT INTO t (id) VALUES (2)")
    rows = await db.fetchall("SELECT id FROM t")
    assert [r["id"] for r in rows] == [1, 2]
    await db.close()


async def test_transaction_rollback_on_error() -> None:
    db = Database(":memory:")
    await db.connect()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    with pytest.raises(DatabaseError):
        async with db.transaction():
            await db.execute("INSERT INTO t (id) VALUES (1)")
            raise RuntimeError("abort")
    rows = await db.fetchall("SELECT id FROM t")
    assert rows == []
    await db.close()


async def test_writes_survive_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "durable.db"
    db = Database(path)
    await db.connect()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    await db.execute("INSERT INTO t (v) VALUES (?)", ("persisted",))
    await db.close()
    reopened = Database(path)
    await reopened.connect()
    try:
        row = await reopened.fetchone("SELECT v FROM t WHERE id = 1")
        assert row is not None
        assert row["v"] == "persisted"
    finally:
        await reopened.close()


async def test_open_database_from_config(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("paths.db_path", str(tmp_path / "app.db"))
    db = await open_database(cfg)
    try:
        await db.execute("CREATE TABLE t (id INTEGER)")
        assert Path(db.path) == tmp_path / "app.db"
    finally:
        await db.close()


async def test_open_database_memory(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("paths.db_path", ":memory:")
    db = await open_database(cfg)
    try:
        assert db.path == ":memory:"
    finally:
        await db.close()
