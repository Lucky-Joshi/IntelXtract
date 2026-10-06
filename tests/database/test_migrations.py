"""Migration runner tests — fresh DB, idempotency, failure isolation."""

from pathlib import Path

import pytest

from core.exceptions import MigrationError
from database.connection import Database
from database.migrations import (
    MIGRATIONS,
    Migration,
    apply,
    current_version,
    migrate,
    validate_migrations,
)

EXPECTED_TABLES = {
    "targets",
    "scans",
    "findings",
    "reports",
    "plugins",
    "api_keys",
    "logs",
    "history",
    "settings",
    "schema_version",
}


async def _table_names(db: Database) -> set[str]:
    rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(r["name"]) for r in rows}


async def test_migrate_creates_all_schema_tables() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        version = await migrate(db)
        assert version == 1
        assert EXPECTED_TABLES.issubset(await _table_names(db))
    finally:
        await db.close()


async def test_migrate_is_idempotent() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        first = await migrate(db)
        second = await migrate(db)
        assert first == second == 1
        rows = await db.fetchall("SELECT version FROM schema_version")
        assert [int(r["version"]) for r in rows] == [1]
    finally:
        await db.close()


async def test_current_version_zero_on_fresh_db() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        assert await current_version(db) == 0
    finally:
        await db.close()


async def test_applied_migrations_records_name() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        await migrate(db)
        applied = await _applied(db)
        assert applied == [(1, "initial schema")]
    finally:
        await db.close()


async def _applied(db: Database) -> list[tuple[int, str]]:
    rows = await db.fetchall(
        "SELECT version, name FROM schema_version ORDER BY version"
    )
    return [(int(r["version"]), str(r["name"])) for r in rows]


async def test_apply_runs_pending_only_in_order() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        extra = Migration(
            version=2, name="extra", sql="CREATE TABLE extra (id INTEGER)"
        )
        final = await apply(db, (*MIGRATIONS, extra))
        assert final == 2
        assert "extra" in await _table_names(db)
        again = await apply(db, (*MIGRATIONS, extra))
        assert again == 2
        assert len(await _applied(db)) == 2
    finally:
        await db.close()


async def test_bad_migration_raises_and_is_not_recorded() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        bad = Migration(version=2, name="bad", sql="CREATE TABLE (;")
        with pytest.raises(MigrationError, match="bad"):
            await apply(db, (*MIGRATIONS, bad))
        assert await current_version(db) == 1
        assert "bad" not in {name for _, name in await _applied(db)}
    finally:
        await db.close()


def test_validate_rejects_empty() -> None:
    with pytest.raises(MigrationError, match="no migrations"):
        validate_migrations(())


def test_validate_rejects_duplicate_versions() -> None:
    migrations = (
        Migration(1, "a", "SELECT 1"),
        Migration(1, "b", "SELECT 1"),
    )
    with pytest.raises(MigrationError, match="duplicate"):
        validate_migrations(migrations)


def test_validate_rejects_non_contiguous_versions() -> None:
    migrations = (Migration(2, "b", "SELECT 1"),)
    with pytest.raises(MigrationError, match=r"1\.\.N"):
        validate_migrations(migrations)


async def test_migrate_on_file_db(tmp_path: Path) -> None:
    path = tmp_path / "data" / "app.db"
    db = Database(path)
    await db.connect()
    try:
        assert await migrate(db) == 1
    finally:
        await db.close()
    assert path.exists()
