"""Repository and persistence round-trip tests on a temp database."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.constants import ModuleStatus, ScanMode, ScanStatus, TargetType
from core.engine import ModuleRun, ScanResult
from core.exceptions import DatabaseError
from core.plugin_loader import PluginRegistry
from database.connection import Database
from database.migrations import migrate
from database.persistence import make_result_sink, save_scan_result, sync_plugins
from database.repositories import Repositories, epoch_to_iso, utc_now

VALID_PLUGIN = """
from core.plugin_loader import PluginBase


class Demo(PluginBase):
    name = "demo"
    version = "1.0.0"
    description = "demo plugin"

    async def run(self, target, ctx):
        return {"echo": target}
"""

BROKEN_PLUGIN = """
raise RuntimeError("boom")
"""


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


def _make_result(
    *,
    target: str = "example.com",
    target_type: TargetType = TargetType.DOMAIN,
    findings: list | None = None,
    scan_id: str = "abc123def456",
) -> ScanResult:
    return ScanResult(
        scan_id=scan_id,
        target=target,
        target_type=target_type,
        mode=ScanMode.QUICK,
        status=ScanStatus.COMPLETED,
        started_at=1_700_000_000.0,
        finished_at=1_700_000_002.5,
        runs=[
            ModuleRun(module="dns", status=ModuleStatus.SUCCESS, duration=1.0),
        ],
        findings=findings if findings is not None else [],
    )


# --- targets -----------------------------------------------------------------


async def test_target_get_or_create_is_stable(repos: Repositories) -> None:
    first = await repos.targets.get_or_create("example.com", "domain")
    second = await repos.targets.get_or_create("example.com", "domain")
    assert first.id == second.id
    other = await repos.targets.get_or_create("example.com", "url")
    assert other.id != first.id


async def test_target_list(repos: Repositories) -> None:
    await repos.targets.get_or_create("a.com", "domain")
    await repos.targets.get_or_create("1.2.3.4", "ip")
    listed = await repos.targets.list()
    assert [t.value for t in listed] == ["a.com", "1.2.3.4"]


# --- scans -------------------------------------------------------------------


async def test_scan_create_and_fetch_roundtrip(repos: Repositories) -> None:
    target = await repos.targets.get_or_create("example.com", "domain")
    scan = await repos.scans.create(
        target_id=target.id,
        uuid="uuid-1",
        mode="quick",
        status="completed",
        started_at=utc_now(),
        duration=1.5,
        runs=[{"module": "dns"}],
    )
    fetched = await repos.scans.get(scan.id)
    assert fetched is not None
    assert fetched.uuid == "uuid-1"
    assert fetched.runs == [{"module": "dns"}]
    by_uuid = await repos.scans.get_by_uuid("uuid-1")
    assert by_uuid is not None
    assert by_uuid.id == scan.id


async def test_scan_create_for_result_persists_fields(
    repos: Repositories,
) -> None:
    result = _make_result(
        findings=[{"module": "dns", "data": {"a": "1.2.3.4"}, "severity": "info"}]
    )
    target = await repos.targets.get_or_create(result.target, result.target_type.value)
    scan = await repos.scans.create_for_result(target.id, result)
    assert scan.uuid == "abc123def456"
    assert scan.mode == "quick"
    assert scan.status == "completed"
    assert scan.duration == pytest.approx(2.5)
    assert scan.started_at == epoch_to_iso(1_700_000_000.0)
    assert scan.runs[0]["module"] == "dns"
    assert await repos.findings.count_for_scan(scan.id) == 0
    written = await repos.findings.bulk_create(scan.id, result.findings)
    assert written == 1
    findings = await repos.findings.list_for_scan(scan.id)
    assert len(findings) == 1
    assert findings[0].data == {"a": "1.2.3.4"}
    assert findings[0].severity == "info"


async def test_scan_list_filters_by_target_and_stats(
    repos: Repositories,
) -> None:
    t1 = await repos.targets.get_or_create("one.com", "domain")
    t2 = await repos.targets.get_or_create("two.com", "domain")
    await repos.scans.create(
        target_id=t1.id,
        uuid="s1",
        mode="quick",
        status="completed",
        started_at=utc_now(),
    )
    await repos.scans.create(
        target_id=t2.id,
        uuid="s2",
        mode="deep",
        status="failed",
        started_at=utc_now(),
    )
    await repos.scans.create(
        target_id=t1.id,
        uuid="s3",
        mode="quick",
        status="completed",
        started_at=utc_now(),
    )
    all_scans = await repos.scans.list()
    assert [s.uuid for s in all_scans] == ["s3", "s2", "s1"]
    only_t1 = await repos.scans.list(target_id=t1.id)
    assert [s.uuid for s in only_t1] == ["s3", "s1"]
    by_status = await repos.scans.list(status="failed")
    assert [s.uuid for s in by_status] == ["s2"]
    latest = await repos.scans.latest_for_target(t1.id)
    assert latest is not None
    assert latest.uuid == "s3"
    stats = await repos.scans.stats()
    assert stats == {"completed": 2, "failed": 1}


async def test_scan_list_detailed_joins_targets(repos: Repositories) -> None:
    t1 = await repos.targets.get_or_create("one.com", "domain")
    t2 = await repos.targets.get_or_create("two.com", "domain")
    await repos.scans.create(
        target_id=t1.id,
        uuid="d1",
        mode="quick",
        status="completed",
        started_at=utc_now(),
    )
    await repos.scans.create(
        target_id=t2.id,
        uuid="d2",
        mode="deep",
        status="failed",
        started_at=utc_now(),
    )
    joined = await repos.scans.list_detailed()
    assert [scan.uuid for scan, _tgt in joined] == ["d2", "d1"]
    assert joined[0][1].value == "two.com"
    assert joined[0][1].type == "domain"
    only_failed = await repos.scans.list_detailed(status="failed")
    assert [scan.uuid for scan, _tgt in only_failed] == ["d2"]
    by_target = await repos.scans.list_detailed(target_value="one.com")
    assert [scan.uuid for scan, _tgt in by_target] == ["d1"]


# --- findings ----------------------------------------------------------------


async def test_findings_bulk_create_roundtrip(
    repos: Repositories,
) -> None:
    target = await repos.targets.get_or_create("x.com", "domain")
    scan = await repos.scans.create(
        target_id=target.id,
        uuid="f1",
        mode="quick",
        status="completed",
        started_at=utc_now(),
    )
    written = await repos.findings.bulk_create(
        scan.id,
        [
            {"module": "dns", "data": {"ip": "1.2.3.4"}},
            {
                "module": "http",
                "data": {"hsts": False},
                "severity": "high",
                "confidence": 0.9,
            },
        ],
    )
    assert written == 2
    findings = await repos.findings.list_for_scan(scan.id)
    assert findings[0].confidence is None
    assert findings[1].severity == "high"
    assert findings[1].confidence == pytest.approx(0.9)
    assert await repos.findings.count_for_scan(scan.id) == 2


async def test_findings_empty_writes_nothing(repos: Repositories) -> None:
    target = await repos.targets.get_or_create("y.com", "domain")
    scan = await repos.scans.create(
        target_id=target.id,
        uuid="f0",
        mode="quick",
        status="completed",
        started_at=utc_now(),
    )
    assert await repos.findings.bulk_create(scan.id, []) == 0
    assert await repos.findings.count_for_scan(scan.id) == 0


async def test_findings_bad_scan_id_enforces_foreign_key(
    repos: Repositories,
) -> None:
    with pytest.raises(DatabaseError):
        await repos.findings.bulk_create(999, [{"module": "dns", "data": {}}])


# --- reports -----------------------------------------------------------------


async def test_report_create_and_list(repos: Repositories) -> None:
    target = await repos.targets.get_or_create("r.com", "domain")
    scan = await repos.scans.create(
        target_id=target.id,
        uuid="r1",
        mode="quick",
        status="completed",
        started_at=utc_now(),
    )
    report = await repos.reports.create(scan.id, "exports/r1.html", "html")
    assert report.format == "html"
    listed = await repos.reports.list_for_scan(scan.id)
    assert [r.path for r in listed] == ["exports/r1.html"]


# --- plugins -----------------------------------------------------------------


async def test_plugin_sync_upsert_and_preserves_enabled(
    repos: Repositories,
) -> None:
    await repos.plugins.sync(
        name="demo", version="1.0.0", api_version=1, source="plugins/demo"
    )
    record = await repos.plugins.get("demo")
    assert record is not None
    assert record.enabled is True
    await repos.plugins.set_enabled("demo", False)
    await repos.plugins.sync(
        name="demo", version="1.1.0", api_version=1, source="plugins/demo"
    )
    record = await repos.plugins.get("demo")
    assert record is not None
    assert record.version == "1.1.0"
    assert record.enabled is False
    assert len(await repos.plugins.list()) == 1


async def test_plugin_set_enabled_unknown_raises(
    repos: Repositories,
) -> None:
    with pytest.raises(DatabaseError, match="unknown plugin"):
        await repos.plugins.set_enabled("nope", True)


# --- api keys ----------------------------------------------------------------


async def test_api_key_store_fetch_delete(repos: Repositories) -> None:
    await repos.api_keys.set("hibp", "ciphertext-abc", hint="abcd")
    record = await repos.api_keys.get("hibp")
    assert record is not None
    assert record.hint == "abcd"
    assert await repos.api_keys.get_ciphertext("hibp") == "ciphertext-abc"
    await repos.api_keys.set("hibp", "ciphertext-xyz", hint="wxyz")
    assert await repos.api_keys.get_ciphertext("hibp") == "ciphertext-xyz"
    assert len(await repos.api_keys.list()) == 1
    assert await repos.api_keys.delete("hibp") is True
    assert await repos.api_keys.get("hibp") is None
    assert await repos.api_keys.delete("hibp") is False


# --- logs & history ----------------------------------------------------------


async def test_log_add_and_recent(repos: Repositories) -> None:
    await repos.logs.add("info", "first", source="core")
    await repos.logs.add("error", "second", source="scan", context={"scan_id": "abc"})
    recent = await repos.logs.recent()
    assert [r.message for r in recent] == ["second", "first"]
    assert recent[1].source == "core"
    assert recent[0].context == {"scan_id": "abc"}


async def test_history_add_and_list(repos: Repositories) -> None:
    target = await repos.targets.get_or_create("h.com", "domain")
    await repos.history.add(target.id, "first_scan", {"count": 1})
    await repos.history.add(target.id, "second_scan", {"count": 2}, scan_id=None)
    events = await repos.history.list_for_target(target.id)
    assert [e.event_type for e in events] == ["second_scan", "first_scan"]
    assert events[1].payload == {"count": 1}


# --- settings ----------------------------------------------------------------


async def test_settings_json_roundtrip(repos: Repositories) -> None:
    assert await repos.settings.get("theme", "dark") == "dark"
    await repos.settings.set("theme", "light")
    await repos.settings.set("limits.rate", 10)
    assert await repos.settings.get("theme") == "light"
    assert await repos.settings.get("limits.rate") == 10
    everything = await repos.settings.all()
    assert everything == {"limits.rate": 10, "theme": "light"}
    assert await repos.settings.delete("theme") is True
    assert await repos.settings.get("theme") is None


# --- persistence -------------------------------------------------------------


async def test_save_scan_result_and_engine_sink(
    db: Database, repos: Repositories
) -> None:
    result = _make_result(
        findings=[
            {"module": "dns", "data": {"a": ["1.2.3.4"]}},
            {"module": "dns", "data": {"mx": ["mail.example.com"]}},
        ]
    )
    scan_id = await save_scan_result(db, result)
    scan = await repos.scans.get(scan_id)
    assert scan is not None
    assert scan.uuid == result.scan_id
    assert (
        scan.target_id
        == (await repos.targets.get_or_create("example.com", "domain")).id
    )
    assert await repos.findings.count_for_scan(scan_id) == 2

    sink = make_result_sink(db)
    second = _make_result(target="other.com", scan_id="def789ghi012")
    await sink(second)
    assert len(await repos.scans.list()) == 2


async def test_sync_plugins_persists_metadata(db: Database, tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "plugin.py").write_text(VALID_PLUGIN, encoding="utf-8")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "plugin.py").write_text(BROKEN_PLUGIN, encoding="utf-8")
    registry = PluginRegistry(tmp_path)
    count = await sync_plugins(db, registry)
    assert count == 2
    repos = Repositories(db)
    demo = await repos.plugins.get("demo")
    broken = await repos.plugins.get("broken")
    assert demo is not None
    assert demo.version == "1.0.0"
    assert demo.enabled is True
    assert broken is not None
    assert broken.error is not None
    await repos.plugins.set_enabled("demo", False)
    await sync_plugins(db, registry)
    demo = await repos.plugins.get("demo")
    assert demo is not None
    assert demo.enabled is False


def test_module_run_status_serializes() -> None:
    run = ModuleRun(module="dns", status=ModuleStatus.SUCCESS, duration=1.0)
    payload = run.to_dict()
    assert json.dumps(payload)
    assert payload["status"] == "success"
