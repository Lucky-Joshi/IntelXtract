"""Forward-only schema migration runner.

Migrations are ordered, immutable, and recorded in ``schema_version``.
The initial schema lives in ``database/schema.sql`` (migration 1); add
future migrations to :data:`MIGRATIONS` — never edit an applied one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.exceptions import DatabaseError, MigrationError
from database.connection import Database

PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = PACKAGE_DIR / "schema.sql"

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    applied_at TEXT    NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """A single forward migration."""

    version: int
    name: str
    sql: str


def _load_initial_sql() -> str:
    try:
        return SCHEMA_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationError(f"cannot read {SCHEMA_FILE}: {exc}") from exc


_MIGRATION_2_SQL = """
ALTER TABLE findings ADD COLUMN title TEXT NOT NULL DEFAULT '';
ALTER TABLE findings ADD COLUMN evidence TEXT NOT NULL DEFAULT '';
ALTER TABLE findings ADD COLUMN content_hash TEXT;
ALTER TABLE findings ADD COLUMN collected_at TEXT;
CREATE INDEX IF NOT EXISTS idx_findings_content_hash ON findings (content_hash);
"""


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="initial schema", sql=_load_initial_sql()),
    Migration(version=2, name="finding normalized fields", sql=_MIGRATION_2_SQL),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def validate_migrations(migrations: Sequence[Migration] = MIGRATIONS) -> None:
    """Ensure migration versions are unique and start at 1."""
    versions = [m.version for m in migrations]
    if not versions:
        raise MigrationError("no migrations defined")
    if len(set(versions)) != len(versions):
        raise MigrationError(f"duplicate migration versions: {versions}")
    if sorted(versions) != list(range(1, len(versions) + 1)):
        raise MigrationError(f"migration versions must be 1..N: {versions}")


async def _ensure_version_table(db: Database) -> None:
    await db.executescript(_BOOTSTRAP_SQL)


async def current_version(db: Database) -> int:
    """Return the highest applied migration version (0 for a fresh db)."""
    await _ensure_version_table(db)
    row = await db.fetchone("SELECT MAX(version) AS v FROM schema_version")
    if row is None or row["v"] is None:
        return 0
    return int(row["v"])


async def applied_migrations(db: Database) -> list[tuple[int, str, str]]:
    """Return applied migrations as (version, name, applied_at) rows."""
    await _ensure_version_table(db)
    rows = await db.fetchall(
        "SELECT version, name, applied_at FROM schema_version ORDER BY version"
    )
    return [(int(r["version"]), str(r["name"]), str(r["applied_at"])) for r in rows]


async def apply(db: Database, migrations: Sequence[Migration] = MIGRATIONS) -> int:
    """Apply every pending migration; returns the final version.

    Raises :class:`MigrationError` (without recording the failure) when a
    migration's SQL is invalid.
    """
    validate_migrations(migrations)
    await _ensure_version_table(db)
    version = await current_version(db)
    ordered = sorted(migrations, key=lambda m: m.version)
    for migration in ordered:
        if migration.version <= version:
            continue
        try:
            await db.executescript(migration.sql)
            await db.execute(
                "INSERT INTO schema_version (version, name, applied_at) "
                "VALUES (?, ?, ?)",
                (migration.version, migration.name, _utc_now()),
            )
        except DatabaseError as exc:
            raise MigrationError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc
        version = migration.version
    return version


async def migrate(db: Database) -> int:
    """Apply the default migration set; returns the final schema version."""
    return await apply(db, MIGRATIONS)
