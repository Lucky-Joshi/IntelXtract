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
    "schedules",
    "cases",
    "case_notes",
    "case_evidence",
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
        assert version == 4
        assert EXPECTED_TABLES.issubset(await _table_names(db))
    finally:
        await db.close()


async def test_migrate_is_idempotent() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        first = await migrate(db)
        second = await migrate(db)
        assert first == second == 4
        rows = await db.fetchall("SELECT version FROM schema_version")
        assert [int(r["version"]) for r in rows] == [1, 2, 3, 4]
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
        assert applied == [
            (1, "initial schema"),
            (2, "finding normalized fields"),
            (3, "recurring schedules"),
            (4, "case management"),
        ]
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
            version=5, name="extra", sql="CREATE TABLE extra (id INTEGER)"
        )
        final = await apply(db, (*MIGRATIONS, extra))
        assert final == 5
        assert "extra" in await _table_names(db)
        again = await apply(db, (*MIGRATIONS, extra))
        assert again == 5
        assert len(await _applied(db)) == 5
    finally:
        await db.close()


async def test_bad_migration_raises_and_is_not_recorded() -> None:
    db = Database(":memory:")
    await db.connect()
    try:
        bad = Migration(version=5, name="bad", sql="CREATE TABLE (;")
        with pytest.raises(MigrationError, match="bad"):
            await apply(db, (*MIGRATIONS, bad))
        assert await current_version(db) == 4
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
        assert await migrate(db) == 4
    finally:
        await db.close()
    assert path.exists()


# --- S26.6: upgrade every released schema version to head ---------------------


async def _build_at_version(version: int) -> Database:
    """Build a fresh database migrated exactly to a released version."""
    db = Database(":memory:")
    await db.connect()
    await apply(db, MIGRATIONS[:version])
    assert await current_version(db) == version
    return db


async def _seed_released_data(
    db: Database, version: int, target: str = "legacy.test"
) -> int:
    """Insert data shaped by the schema shipped at ``version``.

    Returns the seeded finding id so callers can refetch it after upgrading.
    """
    target_cur = await db.execute(
        "INSERT INTO targets (value, type, created_at) VALUES (?, ?, ?)",
        (target, "domain", "2024-01-01T00:00:00Z"),
    )
    scan_cur = await db.execute(
        "INSERT INTO scans (target_id, uuid, mode, status, started_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            int(target_cur.lastrowid or 0),
            f"uuid-{version}",
            "quick",
            "completed",
            "2024-01-01T00:00:01Z",
            "2024-01-01T00:00:01Z",
        ),
    )
    finding_cols = "scan_id, module, severity, confidence, data, created_at"
    placeholders = ", ".join(["?"] * 6)
    params: list[object] = [
        int(scan_cur.lastrowid or 0),
        "dummy",
        "low",
        0.9,
        '{"data": 1}',
        "2024-01-01T00:00:02Z",
    ]
    if version >= 2:
        finding_cols += ", title, evidence, content_hash, collected_at"
        placeholders += ", ?, ?, ?, ?"
        params += [
            "dummy title",
            "parsed:legacy.test",
            "sha256:abc123",
            "2024-01-01T00:00:03Z",
        ]
    finding_cur = await db.execute(
        f"INSERT INTO findings ({finding_cols}) VALUES ({placeholders})",  # noqa: S608
        tuple(params),
    )
    if version >= 3:
        await db.execute(
            "INSERT INTO schedules (target, mode, interval_seconds, enabled, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                target,
                "quick",
                3600,
                1,
                "idle",
                "2024-01-01T00:00:04Z",
                "2024-01-01T00:00:04Z",
            ),
        )
    return int(finding_cur.lastrowid or 0)


@pytest.mark.parametrize("version", [1, 2, 3])
async def test_upgrade_from_every_released_version(version: int) -> None:
    db = await _build_at_version(version)
    try:
        finding_id = await _seed_released_data(db, version)
        final = await apply(db, MIGRATIONS)
        assert final == 4
        assert await current_version(db) == 4
        assert [v for v, _ in await _applied(db)] == [1, 2, 3, 4]

        expected = {
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
            "cases",
            "case_notes",
            "case_evidence",
        }
        if version >= 3:
            expected.add("schedules")
        assert expected.issubset(await _table_names(db))

        row = await db.fetchone(
            "SELECT module, title, evidence, content_hash, collected_at, data "
            "FROM findings WHERE id = ?",
            (finding_id,),
        )
        assert row is not None
        assert row["module"] == "dummy"
        assert row["title"] == ("dummy title" if version >= 2 else "")
        assert row["evidence"] == ("parsed:legacy.test" if version >= 2 else "")
        assert row["content_hash"] == ("sha256:abc123" if version >= 2 else None)
        assert row["collected_at"] == ("2024-01-01T00:00:03Z" if version >= 2 else None)
        assert row["data"] == '{"data": 1}'

        scan = await db.fetchone(
            "SELECT s.status, s.uuid, t.value FROM scans s "
            "JOIN targets t ON t.id = s.target_id WHERE s.uuid = ?",
            (f"uuid-{version}",),
        )
        assert scan is not None
        assert scan["status"] == "completed"
        assert scan["value"] == "legacy.test"

        if version >= 3:
            sched = await db.fetchone(
                "SELECT target, interval_seconds FROM schedules WHERE id = 1"
            )
            assert sched is not None
            assert sched["target"] == "legacy.test"
            assert sched["interval_seconds"] == 3600
    finally:
        await db.close()


async def test_released_data_survives_idempotent_reread() -> None:
    """Re-running the upgrade over an already-head database keeps data."""
    db = await _build_at_version(2)
    try:
        finding_id = await _seed_released_data(db, 2)
        assert await apply(db, MIGRATIONS) == 4
        assert await apply(db, MIGRATIONS) == 4
        row = await db.fetchone(
            "SELECT title, data FROM findings WHERE id = ?", (finding_id,)
        )
        assert row is not None
        assert row["title"] == "dummy title"
        assert row["data"] == '{"data": 1}'
    finally:
        await db.close()
