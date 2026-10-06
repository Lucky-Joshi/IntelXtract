"""Persisting engine results and plugin metadata into the repository layer.

The engine never imports the database; it accepts a ``result_sink`` callable.
:func:`make_result_sink` adapts :class:`Database` to that seam.
"""

from __future__ import annotations

from core.engine import ResultSink, ScanResult
from core.plugin_loader import PluginRegistry
from database.connection import Database
from database.repositories import Repositories


async def save_scan_result(db: Database, result: ScanResult) -> int:
    """Persist a completed scan and its findings; returns the scan id."""
    repos = Repositories(db)
    target = await repos.targets.get_or_create(result.target, result.target_type.value)
    scan = await repos.scans.create_for_result(target.id, result)
    await repos.findings.bulk_create(scan.id, result.findings)
    return scan.id


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
