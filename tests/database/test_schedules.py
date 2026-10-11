"""ScheduleRepository and change-detection persistence tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType
from core.engine import ModuleRun, ScanResult
from core.exceptions import DatabaseError
from core.models import make_finding
from database.connection import Database
from database.migrations import migrate
from database.persistence import record_scan_change, save_scan_result
from database.repositories import Repositories, ScheduleRecord


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = Database(":memory:")
    await database.connect()
    await migrate(database)
    yield database
    await database.close()


@pytest.fixture
def repos(db: Database) -> Repositories:
    return Repositories(db)


async def _require(repos: Repositories, schedule_id: int) -> ScheduleRecord:
    record = await repos.schedules.get(schedule_id)
    assert record is not None
    return record


def _result(
    *,
    target: str = "example.com",
    scan_id: str = "abcdef123456",
    findings: list | None = None,
) -> ScanResult:
    return ScanResult(
        scan_id=scan_id,
        target=target,
        target_type=TargetType.DOMAIN,
        mode=ScanMode.QUICK,
        status=ScanStatus.COMPLETED,
        started_at=1_700_000_000.0,
        finished_at=1_700_000_001.0,
        runs=[ModuleRun(module="dns", status=ModuleStatus.SUCCESS, duration=1.0)],
        findings=findings if findings is not None else [],
    )


# ---------------------------------------------------------------------------
# ScheduleRepository
# ---------------------------------------------------------------------------


async def test_create_and_get_schedule(repos: Repositories) -> None:
    record = await repos.schedules.create(
        "example.com",
        mode="quick",
        interval_seconds=3600,
        next_run_at="2024-01-01T00:00:00+00:00",
    )
    assert record.id >= 1
    assert record.target == "example.com"
    assert record.interval_seconds == 3600
    assert record.enabled is True
    assert record.status == "idle"
    fetched = await repos.schedules.get(record.id)
    assert fetched == record


async def test_get_missing_returns_none(repos: Repositories) -> None:
    assert await repos.schedules.get(999) is None


async def test_due_filters_by_time_and_enabled(repos: Repositories) -> None:
    await repos.schedules.create("due.test", next_run_at="2024-01-01T00:00:00+00:00")
    await repos.schedules.create("later.test", next_run_at="2024-06-01T00:00:00+00:00")
    disabled = await repos.schedules.create(
        "off.test",
        next_run_at="2023-01-01T00:00:00+00:00",
        enabled=False,
    )
    assert disabled.enabled is False

    due = await repos.schedules.due("2024-01-02T00:00:00+00:00")
    assert [s.target for s in due] == ["due.test"]


async def test_due_includes_null_next_run(repos: Repositories) -> None:
    await repos.schedules.create("never.test", next_run_at=None)
    due = await repos.schedules.due("2024-01-01T00:00:00+00:00")
    assert [s.target for s in due] == ["never.test"]


async def test_set_enabled_roundtrip(repos: Repositories) -> None:
    record = await repos.schedules.create("example.com", next_run_at=None)
    await repos.schedules.set_enabled(record.id, False)
    assert (await _require(repos, record.id)).enabled is False
    with pytest.raises(DatabaseError, match="unknown schedule"):
        await repos.schedules.set_enabled(999, True)


async def test_mark_running_and_finished(db: Database, repos: Repositories) -> None:
    record = await repos.schedules.create("example.com", next_run_at=None)
    scan_id = await save_scan_result(db, _result(scan_id="scan00000009"))
    await repos.schedules.mark_running(record.id, "2024-01-01T00:00:00+00:00")
    running = await _require(repos, record.id)
    assert running.status == "running"
    assert running.last_run_at == "2024-01-01T00:00:00+00:00"

    await repos.schedules.mark_finished(
        record.id,
        next_run_at="2024-01-01T01:00:00+00:00",
        scan_id=scan_id,
        error="boom",
    )
    finished = await _require(repos, record.id)
    assert finished.status == "idle"
    assert finished.next_run_at == "2024-01-01T01:00:00+00:00"
    assert finished.last_scan_id == scan_id
    assert finished.last_error == "boom"


async def test_reset_running_recovers_stranded(repos: Repositories) -> None:
    first = await repos.schedules.create("a.test", next_run_at=None)
    second = await repos.schedules.create("b.test", next_run_at=None)
    await repos.schedules.mark_running(first.id, "2024-01-01T00:00:00+00:00")
    await repos.schedules.mark_running(second.id, "2024-01-01T00:00:00+00:00")
    assert await repos.schedules.reset_running() == 2
    assert (await _require(repos, first.id)).status == "idle"
    assert (await _require(repos, second.id)).status == "idle"


async def test_delete(repos: Repositories) -> None:
    record = await repos.schedules.create("example.com", next_run_at=None)
    assert await repos.schedules.delete(record.id) is True
    assert await repos.schedules.delete(record.id) is False


async def test_list_returns_insertion_order(repos: Repositories) -> None:
    await repos.schedules.create("late.test", next_run_at="2024-05-01T00:00:00+00:00")
    await repos.schedules.create("early.test", next_run_at="2024-01-01T00:00:00+00:00")
    await repos.schedules.create("none.test", next_run_at=None)
    listed = await repos.schedules.list()
    assert [s.target for s in listed] == ["late.test", "early.test", "none.test"]


async def test_list_filter_enabled(repos: Repositories) -> None:
    await repos.schedules.create("on.test", next_run_at=None, enabled=True)
    await repos.schedules.create("off.test", next_run_at=None, enabled=False)
    enabled = await repos.schedules.list(enabled=True)
    assert [s.target for s in enabled] == ["on.test"]


# ---------------------------------------------------------------------------
# change detection persistence
# ---------------------------------------------------------------------------


async def test_record_change_baseline_then_diff(
    db: Database, repos: Repositories
) -> None:
    first = _result(
        scan_id="scan00000001",
        findings=[make_finding("dns", "A record").to_dict()],
    )
    scan_one = await save_scan_result(db, first)
    target = await repos.targets.get_or_create("example.com", "domain")

    baseline = await record_scan_change(
        repos,
        target.id,
        previous_scan_id=None,
        current_scan_id=scan_one,
    )
    assert baseline.event_type == "baseline"
    assert baseline.payload["findings"] == 1

    second = _result(
        scan_id="scan00000002",
        findings=[
            make_finding("dns", "A record").to_dict(),
            make_finding("dns", "MX record").to_dict(),
        ],
    )
    scan_two = await save_scan_result(db, second)
    change = await record_scan_change(
        repos,
        target.id,
        previous_scan_id=scan_one,
        current_scan_id=scan_two,
    )
    assert change.event_type == "change"
    assert change.scan_id == scan_two
    assert change.payload["counts"]["added"] == 1
    assert change.payload["previous_scan_id"] == scan_one
    assert change.payload["current_scan_id"] == scan_two
