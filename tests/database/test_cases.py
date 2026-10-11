"""CaseRepository and combined-report payload tests (Phase 22)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType
from core.engine import ModuleRun, ScanResult
from core.exceptions import DatabaseError
from core.models import make_finding
from database.connection import Database
from database.migrations import migrate
from database.persistence import collect_case_payload, save_scan_result
from database.repositories import CaseRecord, Repositories


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


async def _require(repos: Repositories, case_id: int) -> CaseRecord:
    record = await repos.cases.get(case_id)
    assert record is not None
    return record


# ---------------------------------------------------------------------------
# CaseRepository
# ---------------------------------------------------------------------------


async def test_create_and_get_case(repos: Repositories) -> None:
    record = await repos.cases.create("Operation Dawn", description="test case")
    assert record.id >= 1
    assert record.name == "Operation Dawn"
    assert record.description == "test case"
    assert record.status == "open"
    assert await repos.cases.get(record.id) == record
    assert await repos.cases.get_by_name("Operation Dawn") == record


async def test_create_trims_and_rejects_duplicates(repos: Repositories) -> None:
    await repos.cases.create("  spaced  ")
    assert (await repos.cases.get_by_name("spaced")) is not None
    with pytest.raises(DatabaseError, match="already exists"):
        await repos.cases.create("spaced")


async def test_create_rejects_blank_name(repos: Repositories) -> None:
    with pytest.raises(DatabaseError, match="must not be empty"):
        await repos.cases.create("   ")


async def test_get_missing_returns_none(repos: Repositories) -> None:
    assert await repos.cases.get(999) is None
    assert await repos.cases.get_by_name("nope") is None


async def test_resolve_by_id_and_name(repos: Repositories) -> None:
    record = await repos.cases.create("Resolvable")
    assert await repos.cases.resolve(str(record.id)) == record
    assert await repos.cases.resolve("Resolvable") == record
    assert await repos.cases.resolve("missing") is None


async def test_set_status_and_unknown(repos: Repositories) -> None:
    record = await repos.cases.create("Closable")
    await repos.cases.set_status(record.id, "closed")
    assert (await _require(repos, record.id)).status == "closed"
    with pytest.raises(DatabaseError, match="unknown case"):
        await repos.cases.set_status(999, "open")


async def test_notes_roundtrip(repos: Repositories) -> None:
    record = await repos.cases.create("With notes")
    first = await repos.cases.add_note(record.id, "first note")
    second = await repos.cases.add_note(record.id, "second note")
    assert [n.body for n in await repos.cases.list_notes(record.id)] == [
        "first note",
        "second note",
    ]
    assert first.id < second.id
    with pytest.raises(DatabaseError, match="unknown case"):
        await repos.cases.add_note(999, "orphan")


async def test_attach_scan_and_finding(repos: Repositories, db: Database) -> None:
    record = await repos.cases.create("Evidence case")
    scan_id = await save_scan_result(
        db, _result(findings=[make_finding("dns", "A record").to_dict()])
    )
    finding = (await repos.findings.list_for_scan(scan_id))[0]

    scan_evidence = await repos.cases.attach(record.id, scan_id=scan_id, label="seed")
    finding_evidence = await repos.cases.attach(record.id, finding_id=finding.id)

    assert scan_evidence.kind == "scan"
    assert scan_evidence.scan_id == scan_id
    assert scan_evidence.label == "seed"
    assert finding_evidence.kind == "finding"
    assert finding_evidence.finding_id == finding.id

    evidence = await repos.cases.list_evidence(record.id)
    assert [e.id for e in evidence] == [scan_evidence.id, finding_evidence.id]


async def test_attach_requires_reference(repos: Repositories) -> None:
    record = await repos.cases.create("Empty evidence")
    with pytest.raises(DatabaseError, match="requires a scan or finding"):
        await repos.cases.attach(record.id)
    with pytest.raises(DatabaseError, match="unknown case"):
        await repos.cases.attach(999, scan_id=1)


async def test_delete_cascades_notes_and_evidence(
    repos: Repositories, db: Database
) -> None:
    record = await repos.cases.create("Doomed")
    scan_id = await save_scan_result(db, _result())
    await repos.cases.add_note(record.id, "note")
    await repos.cases.attach(record.id, scan_id=scan_id)

    assert await repos.cases.delete(record.id) is True
    assert await repos.cases.delete(record.id) is False
    assert await repos.cases.list_notes(record.id) == []
    assert await repos.cases.list_evidence(record.id) == []


async def test_list_filter_by_status(repos: Repositories) -> None:
    await repos.cases.create("open one")
    second = await repos.cases.create("closed one")
    await repos.cases.set_status(second.id, "closed")
    assert [c.name for c in await repos.cases.list()] == ["open one", "closed one"]
    assert [c.name for c in await repos.cases.list(status="closed")] == ["closed one"]


# ---------------------------------------------------------------------------
# combined report payload
# ---------------------------------------------------------------------------


async def test_collect_case_payload_dedupes_findings(
    repos: Repositories, db: Database
) -> None:
    record = await repos.cases.create("Combined report")
    first = await save_scan_result(
        db,
        _result(
            scan_id="scan00000001",
            findings=[
                make_finding("dns", "A record").to_dict(),
                make_finding("dns", "MX record").to_dict(),
            ],
        ),
    )
    second = await save_scan_result(
        db,
        _result(
            scan_id="scan00000002",
            findings=[make_finding("http", "Server header").to_dict()],
        ),
    )
    finding = (await repos.findings.list_for_scan(first))[0]

    await repos.cases.attach(record.id, scan_id=first)
    await repos.cases.attach(record.id, scan_id=second)
    await repos.cases.attach(record.id, finding_id=finding.id)

    payload = await collect_case_payload(repos, record)
    assert payload["case"] == record
    assert payload["target"] == {"value": "Combined report", "type": "case"}
    assert payload["scan_ids"] == [first, second]
    assert len(payload["evidence"]) == 3
    assert len(payload["findings"]) == 3
    modules = {f["module"] for f in payload["findings"]}
    assert modules == {"dns", "http"}
    assert all("id" in f for f in payload["findings"])


async def test_collect_case_payload_empty(repos: Repositories) -> None:
    record = await repos.cases.create("Nothing attached")
    payload = await collect_case_payload(repos, record)
    assert payload["findings"] == []
    assert payload["scan_ids"] == []
    assert payload["scan"]["uuid"] == f"case-{record.id}"
