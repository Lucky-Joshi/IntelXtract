"""CLI command tests via ``typer.testing.CliRunner``."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cli.main import app
from core.constants import VERSION

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_network_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI scans offline: no real domain modules are registered in tests."""
    monkeypatch.setattr("cli.main._engine_modules", lambda: [])


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
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("INTELXTRACT_CONFIG_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setenv("INTELXTRACT_PATHS__DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("INTELXTRACT_PATHS__EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("INTELXTRACT_PATHS__LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("INTELXTRACT_PATHS__PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("INTELXTRACT_LOGGING__FILE", str(tmp_path / "logs" / "app.log"))
    monkeypatch.setenv("INTELXTRACT_LOGGING__CONSOLE", "false")
    (tmp_path / "plugins").mkdir()
    return tmp_path


def _write_plugin(root: Path, name: str, source: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "plugin.py").write_text(source, encoding="utf-8")
    return directory


def _report_count(cli_env: Path) -> int:
    con = sqlite3.connect(cli_env / "app.db")
    try:
        row = con.execute("SELECT COUNT(*) FROM reports").fetchone()
    finally:
        con.close()
    return int(row[0] or 0)


# --- version / help ----------------------------------------------------------


def test_version_flag(cli_env: Path) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert VERSION in result.stdout


def test_no_args_shows_help(cli_env: Path) -> None:
    result = runner.invoke(app, [])
    assert "scan" in result.stdout


def test_help_lists_commands(cli_env: Path) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "scan",
        "report",
        "history",
        "config",
        "plugin",
        "doctor",
        "update",
    ):
        assert command in result.stdout


# --- scan --------------------------------------------------------------------


def test_scan_console_persists_result(cli_env: Path) -> None:
    result = runner.invoke(app, ["scan", "example.com"])
    assert result.exit_code == 0
    assert "saved as scan #1" in result.stdout
    assert "findings: 0" in result.stdout
    assert (cli_env / "app.db").exists()


def test_scan_json_output(cli_env: Path) -> None:
    result = runner.invoke(app, ["scan", "example.com", "--format", "json"])
    assert result.exit_code == 0
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["target"] == "example.com"
    assert payload["status"] == "completed"
    assert payload["db_scan_id"] == 1


def test_scan_mode_filter(cli_env: Path) -> None:
    result = runner.invoke(
        app, ["scan", "example.com", "-m", "deep", "--format", "json"]
    )
    assert result.exit_code == 0
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["mode"] == "deep"


def test_scan_unknown_module_filter_fails(cli_env: Path) -> None:
    result = runner.invoke(app, ["scan", "example.com", "-M", "dns,http"])
    assert result.exit_code == 1
    assert "unknown module" in result.stderr


def test_scan_invalid_mode_fails(cli_env: Path) -> None:
    result = runner.invoke(app, ["scan", "example.com", "--mode", "bogus"])
    assert result.exit_code == 1
    assert "unknown mode" in result.stderr


def test_scan_empty_target_fails(cli_env: Path) -> None:
    result = runner.invoke(app, ["scan", "   "])
    assert result.exit_code == 1
    assert "empty" in result.stderr


# --- report ------------------------------------------------------------------


def test_report_json_roundtrip(cli_env: Path) -> None:
    assert runner.invoke(app, ["scan", "example.com"]).exit_code == 0
    result = runner.invoke(app, ["report", "1"])
    assert result.exit_code == 0
    report_path = cli_env / "exports" / "report-1.json"
    assert report_path.exists()
    payload: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["scan"]["uuid"]
    assert payload["target"] == {"value": "example.com", "type": "domain"}
    assert payload["findings"] == []
    assert "format: json" in result.stdout


@pytest.mark.parametrize(
    "format_, expected_ext, expected_marker",
    [
        ("html", "html", "<!doctype html>"),
        ("csv", "csv", "severity,module,title,confidence,evidence"),
        ("md", "md", "## Findings"),
        ("json", "json", '"scan"'),
    ],
)
def test_report_formats(
    cli_env: Path,
    tmp_path: Path,
    format_: str,
    expected_ext: str,
    expected_marker: str,
) -> None:
    assert runner.invoke(app, ["scan", "example.com"]).exit_code == 0
    out = tmp_path / f"custom.{expected_ext}"
    result = runner.invoke(app, ["report", "1", "--format", format_, "--out", str(out)])
    assert result.exit_code == 0
    assert expected_marker in out.read_text(encoding="utf-8")
    assert f"format: {format_}" in result.stdout
    assert _report_count(cli_env) >= 1


def test_report_pdf_falls_back_without_weasyprint(
    cli_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("reports.exporter._load_weasyprint_html", lambda: None)
    assert runner.invoke(app, ["scan", "example.com"]).exit_code == 0
    result = runner.invoke(app, ["report", "1", "--format", "pdf"])
    assert result.exit_code == 0
    report_path = cli_env / "exports" / "report-1.html"
    assert report_path.exists()
    assert "<!doctype html>" in report_path.read_text(encoding="utf-8")
    assert "WeasyPrint" in result.stderr
    assert "output: html" in result.stdout


def test_report_unknown_scan_fails(cli_env: Path) -> None:
    result = runner.invoke(app, ["report", "999"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


# --- history -----------------------------------------------------------------


def test_history_list_empty(cli_env: Path) -> None:
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "no scans found" in result.stdout


def test_history_list_and_filters(cli_env: Path) -> None:
    assert runner.invoke(app, ["scan", "example.com"]).exit_code == 0
    assert runner.invoke(app, ["scan", "example.org"]).exit_code == 0
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "example.com" in result.stdout
    assert "2 scan(s)" in result.stdout
    filtered = runner.invoke(app, ["history", "--target", "example.org"])
    assert "example.org" in filtered.stdout
    assert "example.com" not in filtered.stdout
    by_status = runner.invoke(app, ["history", "--status", "completed"])
    assert "2 scan(s)" in by_status.stdout
    none_status = runner.invoke(app, ["history", "--status", "failed"])
    assert "no scans found" in none_status.stdout


def test_history_show(cli_env: Path) -> None:
    assert runner.invoke(app, ["scan", "example.com"]).exit_code == 0
    result = runner.invoke(app, ["history", "show", "1"])
    assert result.exit_code == 0
    assert "example.com" in result.stdout
    assert "uuid=" in result.stdout
    by_uuid = runner.invoke(app, ["history", "show", "1"])
    assert by_uuid.exit_code == 0
    missing = runner.invoke(app, ["history", "show", "nope"])
    assert missing.exit_code == 1
    assert "not found" in missing.stderr


# --- config ------------------------------------------------------------------


def test_config_get_set_list_path(cli_env: Path) -> None:
    get_default = runner.invoke(app, ["config", "get", "scan.max_workers"])
    assert get_default.exit_code == 0
    assert get_default.stdout.strip() == "8"
    set_result = runner.invoke(app, ["config", "set", "scan.max_workers", "4"])
    assert set_result.exit_code == 0
    get_set = runner.invoke(app, ["config", "get", "scan.max_workers"])
    assert get_set.stdout.strip() == "4"
    listed = runner.invoke(app, ["config", "list"])
    assert "scan.max_workers" in listed.stdout
    path_result = runner.invoke(app, ["config", "path"])
    assert str(cli_env / "settings.json") in path_result.stdout


def test_config_get_missing_key_fails(cli_env: Path) -> None:
    result = runner.invoke(app, ["config", "get", "nope.nope"])
    assert result.exit_code == 1
    assert "not set" in result.stderr


# --- plugin ------------------------------------------------------------------


def test_plugin_list_empty(cli_env: Path) -> None:
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "0 plugin(s)" in result.stdout


def test_plugin_list_merges_db_state(cli_env: Path) -> None:
    _write_plugin(cli_env / "plugins", "demo", VALID_PLUGIN)
    _write_plugin(cli_env / "plugins", "broken", BROKEN_PLUGIN)
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    assert "broken" in result.stdout
    assert "2 plugin(s)" in result.stdout


def test_plugin_enable_disable_info(cli_env: Path) -> None:
    _write_plugin(cli_env / "plugins", "demo", VALID_PLUGIN)
    disable = runner.invoke(app, ["plugin", "disable", "demo"])
    assert disable.exit_code == 0
    listed = runner.invoke(app, ["plugin", "list"])
    assert "demo" in listed.stdout
    enable = runner.invoke(app, ["plugin", "enable", "demo"])
    assert enable.exit_code == 0
    info = runner.invoke(app, ["plugin", "info", "demo"])
    assert info.exit_code == 0
    assert "1.0.0" in info.stdout
    missing = runner.invoke(app, ["plugin", "info", "ghost"])
    assert missing.exit_code == 1
    unknown = runner.invoke(app, ["plugin", "enable", "ghost"])
    assert unknown.exit_code == 1
    assert "unknown plugin" in unknown.stderr


# --- doctor ------------------------------------------------------------------


def test_doctor_all_ok(cli_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_network() -> tuple[str, str]:
        return ("ok", "pypi.org reachable")

    monkeypatch.setattr("cli.main._check_network", fake_network)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "all checks passed" in result.stdout


def test_doctor_network_warn_still_passes(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_network() -> tuple[str, str]:
        return ("warn", "network probe failed: offline")

    monkeypatch.setattr("cli.main._check_network", fake_network)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "warn" in result.stdout


# --- update ------------------------------------------------------------------


def test_update_not_published(cli_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch() -> tuple[str | None, str]:
        return (None, "not published")

    monkeypatch.setattr("cli.main._fetch_pypi_version", fake_fetch)
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "not published" in result.stdout


def test_update_available_and_current(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch() -> tuple[str | None, str]:
        return ("9.9.9", "ok")

    monkeypatch.setattr("cli.main._fetch_pypi_version", fake_fetch)
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "update available" in result.stdout
    assert "9.9.9" in result.stdout

    async def fake_current() -> tuple[str | None, str]:
        return (VERSION, "ok")

    monkeypatch.setattr("cli.main._fetch_pypi_version", fake_current)
    current = runner.invoke(app, ["update"])
    assert current.exit_code == 0
    assert "up to date" in current.stdout
