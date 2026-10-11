"""Tests for recurring scheduling — cron math, diffing, and the runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from core.exceptions import ValidationError
from core.scheduling import (
    CronExpression,
    FindingDelta,
    ScheduleRunner,
    ScheduleRunOutcome,
    compute_next_run,
    diff_findings,
    to_iso,
    validate_cadence,
)

# ---------------------------------------------------------------------------
# cron expressions
# ---------------------------------------------------------------------------


def _dt(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def test_cron_requires_five_fields() -> None:
    with pytest.raises(ValidationError, match="5 fields"):
        CronExpression.parse("* * * *")


@pytest.mark.parametrize(
    "expr", ["60 * * * *", "* 24 * * *", "* * 0 * *", "*/0 * * * *"]
)
def test_cron_rejects_out_of_range(expr: str) -> None:
    with pytest.raises(ValidationError):
        CronExpression.parse(expr)


def test_cron_every_five_minutes() -> None:
    cron = CronExpression.parse("*/5 * * * *")
    assert cron.next_after(_dt(2024, 1, 1, 10, 2)) == _dt(2024, 1, 1, 10, 5)
    assert cron.next_after(_dt(2024, 1, 1, 10, 5)) == _dt(2024, 1, 1, 10, 10)


def test_cron_specific_hour_and_minute() -> None:
    cron = CronExpression.parse("30 6 * * *")
    assert cron.next_after(_dt(2024, 3, 10, 7, 0)) == _dt(2024, 3, 11, 6, 30)


def test_cron_weekday_sunday_is_zero() -> None:
    cron = CronExpression.parse("0 0 * * 1")  # Mondays
    # 2024-01-01 is a Monday; from Sunday just before it.
    assert cron.next_after(_dt(2023, 12, 31, 12, 0)) == _dt(2024, 1, 1, 0, 0)


def test_cron_day_or_weekday_semantics() -> None:
    cron = CronExpression.parse("0 0 1 * 1")  # 1st of month OR Monday
    # 2024-05-02 is a Thursday; next match is Monday 2024-05-06.
    assert cron.next_after(_dt(2024, 5, 2, 0, 0)) == _dt(2024, 5, 6, 0, 0)
    # From a Monday, the following Monday matches before June 1st.
    assert cron.next_after(_dt(2024, 5, 6, 0, 0)) == _dt(2024, 5, 13, 0, 0)


def test_cron_month_restriction() -> None:
    cron = CronExpression.parse("0 0 1 12 *")  # Dec 1st
    assert cron.next_after(_dt(2024, 5, 1)) == _dt(2024, 12, 1)


# ---------------------------------------------------------------------------
# cadence
# ---------------------------------------------------------------------------


def test_compute_next_run_interval() -> None:
    after = _dt(2024, 1, 1, 0, 0)
    assert compute_next_run(interval_seconds=90, cron=None, after=after) == _dt(
        2024, 1, 1, 0, 1, 30
    )


def test_compute_next_run_cron() -> None:
    after = _dt(2024, 1, 1, 0, 0)
    assert compute_next_run(
        interval_seconds=None, cron="0 * * * *", after=after
    ) == _dt(2024, 1, 1, 1, 0)


def test_compute_next_run_requires_cadence() -> None:
    with pytest.raises(ValidationError, match="interval or a cron"):
        compute_next_run(interval_seconds=None, cron=None, after=_dt(2024, 1, 1))


def test_validate_cadence_rejects_non_positive() -> None:
    with pytest.raises(ValidationError, match="positive"):
        validate_cadence(interval_seconds=0, cron=None)


def test_validate_cadence_accepts_cron() -> None:
    validate_cadence(interval_seconds=None, cron="*/10 * * * *")


def test_to_iso_is_utc() -> None:
    assert to_iso(_dt(2024, 1, 1, 12, 0)) == "2024-01-01T12:00:00+00:00"


# ---------------------------------------------------------------------------
# change detection
# ---------------------------------------------------------------------------


def _finding(title: str, *, digest: str | None = None, **data: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"module": "m", "title": title, "data": data}
    if digest is not None:
        out["content_hash"] = digest
    return out


def test_diff_detects_added_removed_changed() -> None:
    previous = [
        _finding("keep", digest="a"),
        _finding("gone", digest="x"),
        _finding("edit", digest="1"),
    ]
    current = [
        _finding("keep", digest="a"),
        _finding("edit", digest="2"),
        _finding("new", digest="b"),
    ]
    delta = diff_findings(previous, current)
    assert [f["title"] for f in delta.added] == ["new"]
    assert [f["title"] for f in delta.removed] == ["gone"]
    assert [f["title"] for f in delta.changed] == ["edit"]
    assert not delta.is_empty


def test_diff_uses_data_when_no_hash() -> None:
    previous = [_finding("a", value=1)]
    current = [_finding("a", value=2)]
    delta = diff_findings(previous, current)
    assert [f["title"] for f in delta.changed] == ["a"]


def test_diff_identical_is_empty() -> None:
    findings = [_finding("a", digest="h"), _finding("b", digest="i")]
    delta = diff_findings(findings, list(findings))
    assert delta.is_empty
    assert isinstance(delta, FindingDelta)


def test_diff_payload_counts_and_sorted() -> None:
    previous = [_finding("b", digest="1"), _finding("a", digest="0")]
    current = [_finding("c", digest="9")]
    payload = diff_findings(previous, current).to_payload()
    assert payload["counts"] == {"added": 1, "removed": 2, "changed": 0}
    assert [f["title"] for f in payload["removed"]] == ["a", "b"]


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


@dataclass
class FakeSchedule:
    id: int
    target: str = "example.com"
    mode: str = "quick"
    interval_seconds: int | None = 60
    cron: str | None = None
    next_run_at: str | None = "2024-01-01T00:00:00+00:00"
    enabled: bool = True


class FakeStore:
    """In-memory ScheduleStore recording every call."""

    def __init__(self, schedules: list[FakeSchedule]) -> None:
        self.schedules = {s.id: s for s in schedules}
        self.running: list[tuple[int, str]] = []
        self.finished: list[dict[str, Any]] = []
        self.reset_count = 0

    async def due(self, now: str) -> list[FakeSchedule]:
        return [
            s
            for s in self.schedules.values()
            if s.enabled and (s.next_run_at is None or s.next_run_at <= now)
        ]

    async def mark_running(self, schedule_id: int, started_at: str) -> None:
        self.running.append((schedule_id, started_at))

    async def mark_finished(
        self,
        schedule_id: int,
        *,
        status: str = "idle",
        next_run_at: str | None = None,
        scan_id: int | None = None,
        error: str | None = None,
    ) -> None:
        self.finished.append(
            {
                "id": schedule_id,
                "status": status,
                "next_run_at": next_run_at,
                "scan_id": scan_id,
                "error": error,
            }
        )
        self.schedules[schedule_id].next_run_at = next_run_at

    async def reset_running(self) -> int:
        self.reset_count += 1
        return 0


async def _ok_scan(_schedule: Any) -> ScheduleRunOutcome:
    return ScheduleRunOutcome(scan_id=7)


async def test_run_due_executes_and_advances() -> None:
    schedule = FakeSchedule(id=1, interval_seconds=60)
    store = FakeStore([schedule])
    runner = ScheduleRunner(store, _ok_scan, clock=lambda: 1_704_067_200.0)
    summaries = await runner.run_due()
    assert len(summaries) == 1
    assert summaries[0]["scan_id"] == 7
    assert store.running == [(1, "2024-01-01T00:00:00+00:00")]
    assert store.finished[0]["next_run_at"] == "2024-01-01T00:01:00+00:00"
    assert store.finished[0]["error"] is None


async def test_run_due_skips_not_yet_due() -> None:
    schedule = FakeSchedule(id=1, next_run_at="2024-01-02T00:00:00+00:00")
    store = FakeStore([schedule])
    runner = ScheduleRunner(store, _ok_scan, clock=lambda: 1_704_067_200.0)
    assert await runner.run_due() == []


async def test_run_due_records_error_and_keeps_going() -> None:
    async def _boom(_schedule: Any) -> ScheduleRunOutcome:
        raise RuntimeError("network down")

    schedule = FakeSchedule(id=1)
    store = FakeStore([schedule])
    runner = ScheduleRunner(store, _boom, clock=lambda: 1_704_067_200.0)
    summaries = await runner.run_due()
    assert summaries[0]["error"] == "network down"
    assert store.finished[0]["error"] == "network down"
    assert store.finished[0]["next_run_at"] is not None


async def test_run_due_prevents_overlap() -> None:
    schedule = FakeSchedule(id=1)
    store = FakeStore([schedule])
    inner: dict[str, Any] = {}
    holder: dict[str, ScheduleRunner] = {}

    async def _reentrant(_schedule: Any) -> ScheduleRunOutcome:
        inner["summaries"] = await holder["runner"].run_due()
        return ScheduleRunOutcome(scan_id=1)

    runner = ScheduleRunner(store, _reentrant, clock=lambda: 1_704_067_200.0)
    holder["runner"] = runner
    summaries = await runner.run_due()
    assert inner["summaries"] == []
    assert len(summaries) == 1


async def test_recover_resets_stranded_runs() -> None:
    store = FakeStore([])
    runner = ScheduleRunner(store, _ok_scan)
    assert await runner.recover() == 0
    assert store.reset_count == 1


async def test_run_forever_stops_after_sleep() -> None:
    store = FakeStore([])
    calls = {"sleep": 0}
    holder: dict[str, ScheduleRunner] = {}

    async def _fake_sleep(_seconds: float) -> None:
        calls["sleep"] += 1
        holder["runner"].stop()

    runner = ScheduleRunner(store, _ok_scan, poll_interval=0.01, sleep=_fake_sleep)
    holder["runner"] = runner
    await runner.run_forever()
    assert calls["sleep"] == 1
    assert store.reset_count == 1
