"""Recurring scan scheduling (Phase 21).

Three responsibilities, all independent of the database and the network so
they stay unit-testable:

* **Cadence math** — :func:`compute_next_run` supports fixed intervals and a
  5-field cron subset (:class:`CronExpression`).
* **Change detection** — :func:`diff_findings` compares consecutive scans of
  the same target into added/removed/changed buckets (:class:`FindingDelta`).
* **Runner** — :class:`ScheduleRunner` drains due schedules, prevents
  overlap, advances ``next_run_at`` and recovers interrupted runs. It talks
  to persistence through the :class:`ScheduleStore` protocol.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# cron expressions
# ---------------------------------------------------------------------------

_CRON_BOUNDS: dict[str, tuple[int, int]] = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 6),  # 0 = Sunday, matching crontab(5)
}
_CRON_FIELDS = ("minute", "hour", "day", "month", "weekday")


def _parse_cron_field(
    field_text: str, low: int, high: int
) -> tuple[frozenset[int], bool]:
    """Parse one cron field into (values, restricted)."""
    if not field_text:
        raise ValidationError("empty cron field")
    restricted = field_text != "*"
    values: set[int] = set()
    for part in field_text.split(","):
        step = 1
        if "/" in part:
            base, _, step_raw = part.partition("/")
            try:
                step = int(step_raw)
            except ValueError as exc:
                raise ValidationError(f"invalid cron step: {part!r}") from exc
            if step <= 0:
                raise ValidationError(f"cron step must be positive: {part!r}")
        else:
            base = part
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start_raw, _, end_raw = base.partition("-")
            start, end = _cron_int(start_raw), _cron_int(end_raw)
        else:
            start = end = _cron_int(base)
        if start < low or end > high or start > end:
            raise ValidationError(f"cron value out of range [{low}, {high}]: {part!r}")
        values.update(range(start, end + 1, step))
    return frozenset(values), restricted


def _cron_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationError(f"invalid cron value: {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class CronExpression:
    """A parsed 5-field cron expression (minute hour day month weekday)."""

    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]
    _day_restricted: bool = field(default=False, repr=False)
    _weekday_restricted: bool = field(default=False, repr=False)

    @classmethod
    def parse(cls, expression: str) -> CronExpression:
        """Parse ``"m h dom mon dow"``; raises :class:`ValidationError`."""
        tokens = expression.split()
        if len(tokens) != 5:
            raise ValidationError(
                "cron expression must have 5 fields (minute hour day month weekday)"
            )
        parsed: dict[str, frozenset[int]] = {}
        restricted: dict[str, bool] = {}
        for field_text, name in zip(tokens, _CRON_FIELDS, strict=True):
            low, high = _CRON_BOUNDS[name]
            values, is_restricted = _parse_cron_field(field_text, low, high)
            parsed[name] = values
            restricted[name] = is_restricted
        return cls(
            minute=parsed["minute"],
            hour=parsed["hour"],
            day=parsed["day"],
            month=parsed["month"],
            weekday=parsed["weekday"],
            _day_restricted=restricted["day"],
            _weekday_restricted=restricted["weekday"],
        )

    def day_matches(self, moment: datetime) -> bool:
        """Whether the day-of-month/weekday fields match ``moment``."""
        dom_ok = moment.day in self.day
        cron_dow = (moment.weekday() + 1) % 7  # Monday=0 → Sunday=0
        dow_ok = cron_dow in self.weekday
        if self._day_restricted and self._weekday_restricted:
            return dom_ok or dow_ok  # crontab OR semantics
        return dom_ok and dow_ok

    def next_after(self, after: datetime) -> datetime:
        """The first minute strictly after ``after`` that matches."""
        base = after.replace(second=0, microsecond=0)
        first_day = base.replace(hour=0, minute=0)
        for offset in range(0, 366 * 4 + 1):
            day = first_day + timedelta(days=offset)
            if day.month not in self.month or not self.day_matches(day):
                continue
            for hour in sorted(self.hour):
                for minute in sorted(self.minute):
                    candidate = day.replace(hour=hour, minute=minute)
                    if candidate > base:
                        return candidate
        raise ValidationError("cron expression did not match within four years")


# ---------------------------------------------------------------------------
# cadence
# ---------------------------------------------------------------------------


def compute_next_run(
    *,
    interval_seconds: int | None,
    cron: str | None,
    after: datetime,
) -> datetime:
    """Return the next run time after ``after`` for an interval or cron."""
    if cron:
        return CronExpression.parse(cron).next_after(after)
    if interval_seconds:
        if interval_seconds <= 0:
            raise ValidationError("interval_seconds must be positive")
        return after + timedelta(seconds=interval_seconds)
    raise ValidationError("schedule requires an interval or a cron expression")


def validate_cadence(*, interval_seconds: int | None, cron: str | None) -> None:
    """Ensure a schedule declares exactly one usable cadence."""
    if interval_seconds is None and not cron:
        raise ValidationError("schedule requires --every or --cron")
    if interval_seconds is not None and interval_seconds <= 0:
        raise ValidationError("interval_seconds must be positive")
    if cron is not None:
        CronExpression.parse(cron)


def to_iso(moment: datetime) -> str:
    """Format an aware datetime as an ISO-8601 UTC string."""
    return moment.astimezone(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# change detection (S21.3)
# ---------------------------------------------------------------------------


def _finding_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (str(item.get("module") or ""), str(item.get("title") or ""))


def _finding_signature(item: Mapping[str, Any]) -> str:
    digest = item.get("content_hash")
    if digest:
        return str(digest)
    return json.dumps(item.get("data") or {}, sort_keys=True, default=str)


@dataclass(frozen=True, slots=True)
class FindingDelta:
    """Added/removed/changed findings between two scans."""

    added: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    changed: list[dict[str, Any]]

    @property
    def is_empty(self) -> bool:
        """True when the two scans produced identical finding sets."""
        return not (self.added or self.removed or self.changed)

    def to_payload(self) -> dict[str, Any]:
        """JSON-serializable payload for a ``history`` event."""
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "counts": {
                "added": len(self.added),
                "removed": len(self.removed),
                "changed": len(self.changed),
            },
        }


def diff_findings(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
) -> FindingDelta:
    """Diff two scans' findings keyed by ``(module, title)``.

    A finding present in both scans is *changed* when its signature
    (``content_hash``, else the JSON of ``data``) differs. Output is sorted
    by ``(module, title)`` for deterministic history payloads.
    """
    prev = {_finding_key(item): item for item in previous}
    curr = {_finding_key(item): item for item in current}

    def _sorted(keys: Any, source: dict[tuple[str, str], Mapping[str, Any]]) -> list:
        return [dict(source[key]) for key in sorted(keys)]

    added = _sorted(curr.keys() - prev.keys(), curr)
    removed = _sorted(prev.keys() - curr.keys(), prev)
    changed = _sorted(
        (
            key
            for key in curr.keys() & prev.keys()
            if _finding_signature(curr[key]) != _finding_signature(prev[key])
        ),
        curr,
    )
    return FindingDelta(added=added, removed=removed, changed=changed)


# ---------------------------------------------------------------------------
# runner (S21.2)
# ---------------------------------------------------------------------------


@runtime_checkable
class ScheduleLike(Protocol):
    """Structural view of a persisted schedule used by the runner."""

    @property
    def id(self) -> int: ...
    @property
    def target(self) -> str: ...
    @property
    def mode(self) -> str: ...
    @property
    def interval_seconds(self) -> int | None: ...
    @property
    def cron(self) -> str | None: ...
    @property
    def next_run_at(self) -> str | None: ...


class ScheduleStore(Protocol):
    """Persistence seam for the runner (implemented by ``ScheduleRepository``)."""

    async def due(self, now: str) -> Sequence[ScheduleLike]: ...

    async def mark_running(self, schedule_id: int, started_at: str) -> None: ...

    async def mark_finished(
        self,
        schedule_id: int,
        *,
        status: str = "idle",
        next_run_at: str | None = None,
        scan_id: int | None = None,
        error: str | None = None,
    ) -> None: ...

    async def reset_running(self) -> int: ...


@dataclass(slots=True)
class ScheduleRunOutcome:
    """What a single scheduled scan produced."""

    scan_id: int | None = None
    error: str | None = None


RunSchedule = Callable[[ScheduleLike], Awaitable[ScheduleRunOutcome]]
Clock = Callable[[], float]


class ScheduleRunner:
    """Drains due schedules and advances their cadence.

    ``run_scan`` performs the actual scan (and any persistence/change
    detection) and reports back a :class:`ScheduleRunOutcome`. The runner
    owns overlap prevention: an in-flight schedule is skipped and, across
    processes, rows are flagged ``running`` in the store.
    """

    def __init__(
        self,
        store: ScheduleStore,
        run_scan: RunSchedule,
        *,
        clock: Clock = time.time,
        poll_interval: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._store = store
        self._run_scan = run_scan
        self._clock = clock
        self._poll_interval = poll_interval
        self._sleep = sleep
        self._inflight: set[int] = set()
        self._stop = asyncio.Event()

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), tz=UTC)

    async def recover(self) -> int:
        """Reset schedules stranded mid-run so their next tick resumes them."""
        return await self._store.reset_running()

    async def run_due(self, *, now: float | None = None) -> list[dict[str, Any]]:
        """Run every due schedule once; returns per-schedule summaries."""
        when = self._now() if now is None else datetime.fromtimestamp(now, tz=UTC)
        summaries: list[dict[str, Any]] = []
        for schedule in await self._store.due(to_iso(when)):
            if schedule.id in self._inflight:
                continue
            self._inflight.add(schedule.id)
            try:
                summaries.append(await self._run_one(schedule))
            finally:
                self._inflight.discard(schedule.id)
        return summaries

    async def _run_one(self, schedule: ScheduleLike) -> dict[str, Any]:
        started = self._now()
        await self._store.mark_running(schedule.id, to_iso(started))
        outcome = ScheduleRunOutcome()
        try:
            outcome = await self._run_scan(schedule)
        except Exception as exc:  # a failed run must not stop the loop
            outcome = ScheduleRunOutcome(error=str(exc))
        next_run_at = self._advance(schedule, self._now())
        await self._store.mark_finished(
            schedule.id,
            status="idle",
            next_run_at=next_run_at,
            scan_id=outcome.scan_id,
            error=outcome.error,
        )
        return {
            "schedule_id": schedule.id,
            "target": schedule.target,
            "scan_id": outcome.scan_id,
            "error": outcome.error,
            "next_run_at": next_run_at,
        }

    @staticmethod
    def _advance(schedule: ScheduleLike, after: datetime) -> str | None:
        try:
            return to_iso(
                compute_next_run(
                    interval_seconds=schedule.interval_seconds,
                    cron=schedule.cron,
                    after=after,
                )
            )
        except ValidationError:
            return None

    async def run_forever(self, *, recover: bool = True) -> None:
        """Poll until :meth:`stop`; recover interrupted runs on entry."""
        self._stop.clear()
        if recover:
            await self.recover()
        while not self._stop.is_set():
            await self.run_due()
            await self._sleep(self._poll_interval)

    def stop(self) -> None:
        """Request the polling loop to exit after the current tick."""
        self._stop.set()
