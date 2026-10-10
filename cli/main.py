"""IntelXtract command-line interface.

Every command is a thin synchronous wrapper around an ``async`` body run with
``asyncio.run`` so the Typer/Click runner stays simple and testable.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, NoReturn

import aiohttp
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from core.config import Config, load_config
from core.constants import VERSION, ScanMode
from core.engine import ModuleRun, ScanEngine, ScanResult
from core.exceptions import (
    ConfigError,
    DatabaseError,
    MigrationError,
    PluginLoadError,
    ScanError,
    ValidationError,
)
from core.logger import setup_logging
from core.plugin_loader import PluginRegistry
from database.connection import Database, open_database
from database.migrations import migrate
from database.persistence import make_result_sink
from database.repositories import Repositories, ScanRecord
from modules.registry import ModuleRegistry
from reports import build_report, export_report

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="intelxtract",
    help="IntelXtract — AI-powered OSINT automation platform.",
    no_args_is_help=True,
    add_completion=False,
)
history_app = typer.Typer(help="Inspect past scans.", no_args_is_help=False)
config_app = typer.Typer(help="Get/set configuration values.", no_args_is_help=True)
plugin_app = typer.Typer(help="Manage plugins.", no_args_is_help=True)
app.add_typer(history_app, name="history")
app.add_typer(config_app, name="config")
app.add_typer(plugin_app, name="plugin")

StatusColor = {"ok": "green", "warn": "yellow", "fail": "red"}
ScanStatusColor = {
    "completed": "green",
    "failed": "red",
    "cancelled": "yellow",
    "running": "blue",
    "pending": "dim",
}
ModuleStatusColor = {
    "success": "green",
    "failed": "red",
    "timeout": "yellow",
    "skipped": "dim",
    "cancelled": "yellow",
    "pending": "dim",
    "running": "blue",
}


def _fail(message: str, code: int = 1) -> NoReturn:
    """Print an error to stderr and exit with ``code``."""
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=code)


def _version_callback(value: bool) -> None:
    """Eager ``--version`` handler (runs before command dispatch)."""
    if value:
        typer.echo(VERSION)
        raise typer.Exit()


def _parse_value(raw: str) -> Any:
    """Parse a CLI value as JSON when possible, else keep it as a string."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _split_modules(raw: str | None) -> list[str] | None:
    """Split a comma-separated module filter into a clean list."""
    if raw is None:
        return None
    names = [part.strip() for part in raw.split(",") if part.strip()]
    return names or None


def _engine_modules() -> list[Any]:
    """Discover registered scan modules for engine construction.

    Hard failures are surfaced via a printed warning rather than aborting the
    scan, matching the fail-soft philosophy of the plugin loader.
    """
    try:
        registry = ModuleRegistry(
            packages=(
                "modules.domain",
                "modules.ip",
                "modules.website",
                "modules.email",
                "modules.username",
                "modules.certificate",
                "modules.metadata",
                "modules.news",
            )
        )
        return registry.instances()
    except Exception as exc:  # fail-soft: keep scans usable offline
        console.print(f"[yellow]warning:[/yellow] module discovery failed: {exc}")
        return []


def _load_config(db_override: str | None = None) -> Config:
    """Load layered config, optionally overriding the database path."""
    try:
        cfg = load_config()
    except ConfigError as exc:
        _fail(str(exc))
    if db_override is not None:
        cfg.set("paths.db_path", db_override)
    return cfg


async def _open_db(cfg: Config) -> Database:
    """Open the configured database and apply migrations."""
    try:
        db = await open_database(cfg)
        await migrate(db)
    except (DatabaseError, MigrationError, OSError) as exc:
        _fail(f"cannot open database: {exc}")
    return db


async def _resolve_scan(repos: Repositories, ref: str) -> ScanRecord | None:
    """Look up a scan by integer database id or engine uuid."""
    if ref.isdigit():
        return await repos.scans.get(int(ref))
    return await repos.scans.get_by_uuid(ref)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested config into dotted keys."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, dotted))
        else:
            out[dotted] = value
    return out


def _registry(cfg: Config) -> PluginRegistry:
    """Build a plugin registry from the configured plugins directory."""
    directory = Path(str(cfg.get("paths.plugins_dir", "plugins"))).expanduser()
    return PluginRegistry(directory)


def _default_report_path(cfg: Config, scan_id: int, extension: str) -> Path:
    """Default export path for a scan report: ``exports/report-<id>.<ext>``."""
    exports = Path(str(cfg.get("paths.exports_dir", "exports"))).expanduser()
    return exports / f"report-{scan_id}.{extension}"


def _write_report_bytes(out_path: Path, data: bytes) -> None:
    """Write report bytes to disk (sync helper for thread offload)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)


def _resolve_db_path(raw: str) -> str:
    """Expand a database path (sync helper for thread offload)."""
    return raw if raw == ":memory:" else str(Path(raw).expanduser())


@app.callback()
def main(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug logging."
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """IntelXtract command-line interface."""
    if verbose:
        os.environ["INTELXTRACT_LOGGING__LEVEL"] = "DEBUG"
    try:
        cfg = load_config()
        setup_logging(cfg)
    except ConfigError as exc:
        err_console.print(f"[yellow]config:[/yellow] {exc}")


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


@app.command()
def scan(
    target: str = typer.Argument(..., help="Target to scan (domain, IP, URL, ...)."),
    mode: str | None = typer.Option(
        None, "--mode", "-m", help="Scan profile: quick|deep|custom."
    ),
    modules: str | None = typer.Option(
        None, "--modules", "-M", help="Comma-separated module name filter."
    ),
    output_format: str = typer.Option(
        "console", "--format", "-f", help="Output format: console|json."
    ),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Scan a target and persist the structured result."""
    asyncio.run(_scan(target, mode, modules, output_format, db))


async def _scan(
    target: str,
    mode_raw: str | None,
    modules_raw: str | None,
    output_format: str,
    db_override: str | None,
) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        try:
            mode = ScanMode(mode_raw or str(cfg.get("scan.default_mode", "quick")))
        except ValueError:
            _fail(f"unknown mode: {mode_raw!r}" " (use quick|deep|custom)")
        module_names = _split_modules(modules_raw)
        events: list[ModuleRun] = []
        holder: dict[str, Any] = {}

        def _on_done(run: ModuleRun) -> None:
            events.append(run)
            progress = holder.get("progress")
            if progress is not None:
                progress.update(
                    holder["task"],
                    completed=len(events),
                    description=f"{run.module} → {run.status.value}",
                )

        engine = ScanEngine(
            cfg,
            modules=_engine_modules(),
            result_sink=make_result_sink(db),
            on_module_done=_on_done,
        )
        names = engine.module_names()
        try:
            if names:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    holder["progress"] = progress
                    holder["task"] = progress.add_task("scanning", total=len(names))
                    result = await engine.scan(
                        target, mode=mode, module_names=module_names
                    )
            else:
                err_console.print(
                    "[yellow]note:[/yellow] no modules registered yet"
                    " (collection modules land in Phase 6+)"
                )
                result = await engine.scan(target, mode=mode, module_names=module_names)
        except (ValidationError, ScanError) as exc:
            _fail(str(exc))
        if output_format == "json":
            repos = Repositories(db)
            row = await repos.scans.get_by_uuid(result.scan_id)
            payload = result.to_dict()
            payload["db_scan_id"] = row.id if row is not None else None
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            return
        if output_format != "console":
            _fail(f"unknown format: {output_format!r} (use console|json)")
        repos = Repositories(db)
        row = await repos.scans.get_by_uuid(result.scan_id)
        _render_scan_result(result, row.id if row is not None else None)
    finally:
        await db.close()


def _render_scan_result(result: ScanResult, db_id: int | None) -> None:
    """Print a scan summary, module table, and findings count."""
    status = result.status.value
    color = ScanStatusColor.get(status, "white")
    console.print(
        f"[bold]scan[/bold] {result.scan_id}  "
        f"status=[{color}]{status}[/{color}]  "
        f"duration={result.duration:.2f}s  "
        f"target={result.target} ({result.target_type.value})  "
        f"mode={result.mode.value}"
    )
    if db_id is not None:
        console.print(f"saved as scan [bold]#{db_id}[/bold]")
    table = Table("module", "status", "duration", "error")
    for run in result.runs:
        run_color = ModuleStatusColor.get(run.status.value, "white")
        table.add_row(
            run.module,
            f"[{run_color}]{run.status.value}[/{run_color}]",
            f"{run.duration:.2f}s",
            (run.error or "-")[:60],
        )
    console.print(table)
    console.print(f"findings: [bold]{len(result.findings)}[/bold]")


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@app.command()
def report(
    scan_id: str = typer.Argument(..., help="Scan id (database id or uuid)."),
    output_format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Report format: json|html|pdf|csv|md.",
    ),
    out: Path | None = typer.Option(None, "--out", help="Output file path."),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Generate or export a report for a past scan."""
    asyncio.run(_report(scan_id, output_format, out, db))


async def _report(
    scan_id: str,
    output_format: str,
    out: Path | None,
    db_override: str | None,
) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        repos = Repositories(db)
        scan = await _resolve_scan(repos, scan_id)
        if scan is None:
            _fail(f"scan not found: {scan_id}")
        target = await repos.targets.get(scan.target_id)
        findings = await repos.findings.list_for_scan(scan.id)
        payload: dict[str, Any] = {
            "scan": {
                "id": scan.id,
                "uuid": scan.uuid,
                "mode": scan.mode,
                "status": scan.status,
                "started_at": scan.started_at,
                "finished_at": scan.finished_at,
                "duration": scan.duration,
                "error": scan.error,
                "runs": scan.runs,
            },
            "target": (
                {"value": target.value, "type": target.type} if target else None
            ),
            "findings": [
                {
                    "module": finding.module,
                    "title": finding.title,
                    "severity": finding.severity,
                    "confidence": finding.confidence,
                    "data": finding.data,
                    "evidence": finding.evidence,
                    "created_at": finding.created_at,
                }
                for finding in findings
            ],
        }
        model = build_report(payload["scan"], payload["target"], payload["findings"])
        exported = await asyncio.to_thread(export_report, model, output_format)
        if exported.warning:
            err_console.print(f"[yellow]warning:[/yellow] {exported.warning}")
        extension = "pdf" if exported.format == "pdf" else exported.format
        if out is not None:
            out_path = out
        else:
            out_path = await asyncio.to_thread(
                _default_report_path, cfg, scan.id, extension
            )
        await asyncio.to_thread(_write_report_bytes, out_path, exported.data)
        await repos.reports.create(scan.id, str(out_path), output_format)
        console.print(
            f"report written to [bold]{out_path}[/bold]"
            f" (format: {output_format}; output: {exported.format})"
        )
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


@history_app.callback(invoke_without_command=True)
def history_list(
    ctx: typer.Context,
    target: str | None = typer.Option(
        None, "--target", "-t", help="Filter by target value."
    ),
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by scan status."
    ),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=500),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """List past scans (newest first)."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_history_list(target, status, limit, db))


async def _history_list(
    target: str | None,
    status: str | None,
    limit: int,
    db_override: str | None,
) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        repos = Repositories(db)
        joined = await repos.scans.list_detailed(
            limit=limit, target_value=target, status=status
        )
        if not joined:
            console.print("no scans found")
            return
        table = Table("id", "uuid", "target", "type", "mode", "status", "started")
        for scan, tgt in joined:
            color = ScanStatusColor.get(scan.status, "white")
            table.add_row(
                str(scan.id),
                scan.uuid,
                tgt.value,
                tgt.type,
                scan.mode,
                f"[{color}]{scan.status}[/{color}]",
                scan.started_at,
            )
        console.print(table)
        console.print(f"{len(joined)} scan(s)")
    finally:
        await db.close()


@history_app.command("show")
def history_show(
    scan_id: str = typer.Argument(..., help="Scan id (database id or uuid)."),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Show full detail for one scan."""
    asyncio.run(_history_show(scan_id, db))


async def _history_show(scan_id: str, db_override: str | None) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        repos = Repositories(db)
        scan = await _resolve_scan(repos, scan_id)
        if scan is None:
            _fail(f"scan not found: {scan_id}")
        target = await repos.targets.get(scan.target_id)
        findings = await repos.findings.list_for_scan(scan.id)
        reports = await repos.reports.list_for_scan(scan.id)
        color = ScanStatusColor.get(scan.status, "white")
        console.print(
            f"[bold]scan[/bold] #{scan.id}  uuid={scan.uuid}  "
            f"status=[{color}]{scan.status}[/{color}]  mode={scan.mode}"
        )
        if target is not None:
            console.print(f"target: {target.value} ({target.type})")
        console.print(
            f"started: {scan.started_at}  finished: {scan.finished_at}"
            f"  duration: {scan.duration:.2f}s"
        )
        if scan.error:
            console.print(f"error: [red]{scan.error}[/red]")
        runs_table = Table("module", "status", "duration", "error")
        for run in scan.runs:
            run_color = ModuleStatusColor.get(str(run.get("status", "")), "white")
            runs_table.add_row(
                str(run.get("module", "-")),
                f"[{run_color}]{run.get('status', '-')}[/{run_color}]",
                f"{float(run.get('duration', 0) or 0):.2f}s",
                str(run.get("error") or "-")[:60],
            )
        console.print(runs_table)
        findings_table = Table("#", "module", "severity", "confidence", "data")
        for finding in findings:
            findings_table.add_row(
                str(finding.id),
                finding.module,
                finding.severity or "-",
                (
                    f"{finding.confidence:.2f}"
                    if finding.confidence is not None
                    else "-"
                ),
                json.dumps(finding.data, ensure_ascii=False, default=str)[:60],
            )
        console.print(findings_table)
        console.print(f"findings: {len(findings)}  reports: {len(reports)}")
        for report_row in reports:
            console.print(f"  report: {report_row.format} → {report_row.path}")
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="Dotted config key.")) -> None:
    """Print one configuration value."""
    cfg = _load_config()
    value = cfg.get(key, None)
    if value is None:
        _fail(f"config key not set: {key}")
    typer.echo(value if isinstance(value, str) else json.dumps(value))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dotted config key."),
    value: str = typer.Argument(..., help="New value (JSON-parsed when possible)."),
) -> None:
    """Set a configuration value and persist it."""
    cfg = _load_config()
    cfg.set(key, _parse_value(value))
    cfg.save()
    console.print(f"{key} = {cfg.get(key)}")


@config_app.command("list")
def config_list() -> None:
    """Show the effective configuration as dotted keys."""
    cfg = _load_config()
    rows = _flatten(cfg.as_dict())
    table = Table("key", "value")
    for key in sorted(rows):
        value = rows[key]
        table.add_row(
            key,
            value if isinstance(value, str) else json.dumps(value, default=str),
        )
    console.print(table)
    console.print(f"config file: {cfg.path}")


@config_app.command("path")
def config_path() -> None:
    """Print the path of the configuration file."""
    console.print(str(_load_config().path))


# ---------------------------------------------------------------------------
# plugin
# ---------------------------------------------------------------------------


@plugin_app.command("list")
def plugin_list(
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """List discovered plugins and their persisted state."""
    asyncio.run(_plugin_list(db))


async def _plugin_list(db_override: str | None) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        repos = Repositories(db)
        registry = _registry(cfg)
        infos = registry.discover()
        db_rows = {row.name: row for row in await repos.plugins.list()}
        registry.apply_state({name: row.enabled for name, row in db_rows.items()})
        table = Table("name", "version", "api", "enabled", "error")
        for info in infos:
            row = db_rows.get(info.name)
            enabled = row.enabled if row else registry.is_enabled(info.name)
            error = info.error or (row.error if row else None)
            table.add_row(
                info.name,
                info.version,
                str(info.api_version),
                "yes" if enabled else "no",
                error or "-",
            )
        console.print(table)
        console.print(f"{len(infos)} plugin(s) in {registry.directory}")
    finally:
        await db.close()


@plugin_app.command("info")
def plugin_info(
    name: str = typer.Argument(..., help="Plugin name."),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Show details for one plugin."""
    asyncio.run(_plugin_info(name, db))


async def _plugin_info(name: str, db_override: str | None) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        repos = Repositories(db)
        registry = _registry(cfg)
        infos = registry.discover()
        info = next((i for i in infos if i.name == name), None)
        if info is None:
            _fail(f"unknown plugin: {name}")
        row = await repos.plugins.get(name)
        enabled = row.enabled if row else registry.is_enabled(name)
        error = info.error or (row.error if row else None) or "-"
        table = Table("field", "value")
        table.add_row("name", info.name)
        table.add_row("version", info.version)
        table.add_row("api_version", str(info.api_version))
        table.add_row("author", info.author or "-")
        table.add_row("description", info.description or "-")
        table.add_row("source", str(info.source))
        table.add_row(
            "target_types",
            ", ".join(t.value for t in info.target_types) or "-",
        )
        table.add_row("required_keys", ", ".join(info.requires_keys) or "-")
        table.add_row("enabled", "yes" if enabled else "no")
        table.add_row("error", error)
        console.print(table)
    finally:
        await db.close()


@plugin_app.command("enable")
def plugin_enable(
    name: str = typer.Argument(..., help="Plugin name."),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Enable a plugin and persist the flag."""
    asyncio.run(_plugin_toggle(name, True, db))


@plugin_app.command("disable")
def plugin_disable(
    name: str = typer.Argument(..., help="Plugin name."),
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Disable a plugin and persist the flag."""
    asyncio.run(_plugin_toggle(name, False, db))


async def _plugin_toggle(name: str, enable: bool, db_override: str | None) -> None:
    cfg = _load_config(db_override)
    db = await _open_db(cfg)
    try:
        repos = Repositories(db)
        registry = _registry(cfg)
        infos = registry.discover()
        info = next((i for i in infos if i.name == name), None)
        if info is None:
            _fail(f"unknown plugin: {name}")
        try:
            if enable:
                registry.enable(name)
            else:
                registry.disable(name)
        except PluginLoadError as exc:
            _fail(str(exc))
        existing = await repos.plugins.get(name)
        if existing is not None:
            await repos.plugins.set_enabled(name, enable)
        else:
            await repos.plugins.sync(
                name=info.name,
                version=info.version,
                api_version=info.api_version,
                source=str(info.source),
                description=info.description,
                error=info.error,
                enabled=enable,
            )
        verb = "enabled" if enable else "disabled"
        console.print(f"plugin [bold]{name}[/bold] {verb}")
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def _check_python() -> tuple[str, str]:
    version = sys.version_info
    detail = f"Python {platform.python_version()}"
    if version >= (3, 13):
        return ("ok", detail)
    return ("fail", f"{detail} (>= 3.13 required)")


def _check_venv() -> tuple[str, str]:
    base = getattr(sys, "base_prefix", sys.prefix)
    in_venv = sys.prefix != base or bool(os.environ.get("VIRTUAL_ENV"))
    if in_venv:
        return ("ok", f"venv active ({sys.prefix})")
    return ("warn", "not running inside a virtualenv")


def _check_config() -> tuple[str, str]:
    try:
        cfg = load_config()
    except ConfigError as exc:
        return ("fail", str(exc))
    return ("ok", f"config loaded from {cfg.path}")


def _check_dependencies() -> tuple[str, str]:
    missing: list[str] = []
    versions: list[str] = []
    for dist in ("aiohttp", "aiosqlite", "typer", "rich", "jinja2"):
        try:
            versions.append(f"{dist}=={importlib.metadata.version(dist)}")
        except importlib.metadata.PackageNotFoundError:
            missing.append(dist)
    if missing:
        return ("fail", f"missing: {', '.join(missing)}")
    return ("ok", ", ".join(versions))


async def _check_db(cfg: Config) -> tuple[str, str]:
    raw = str(cfg.get("paths.db_path", ":memory:"))
    path = await asyncio.to_thread(_resolve_db_path, raw)
    db = Database(path)
    try:
        await db.connect()
        await migrate(db)
        probe = "__doctor_probe__"
        await db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (probe, "1", "1970-01-01T00:00:00+00:00"),
        )
        await db.execute("DELETE FROM settings WHERE key = ?", (probe,))
    except (DatabaseError, MigrationError, OSError) as exc:
        return ("fail", f"database check failed: {exc}")
    finally:
        await db.close()
    return ("ok", f"database writable at {db.path}")


async def _check_network() -> tuple[str, str]:
    """Reachability probe against PyPI (fail-soft: warnings only)."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://pypi.org/pypi/typer/json") as resp:
                if resp.status == 200:
                    return ("ok", "pypi.org reachable")
                return ("warn", f"pypi.org returned HTTP {resp.status}")
    except Exception as exc:
        return ("warn", f"network probe failed: {exc}")


@app.command()
def doctor(
    db: str | None = typer.Option(None, "--db", help="Override the database path."),
) -> None:
    """Run environment diagnostics."""
    asyncio.run(_doctor(db))


async def _doctor(db_override: str | None) -> None:
    cfg = _load_config(db_override)
    checks: list[tuple[str, tuple[str, str]]] = [
        ("python", _check_python()),
        ("venv", _check_venv()),
        ("config", _check_config()),
        ("dependencies", _check_dependencies()),
        ("database", await _check_db(cfg)),
        ("network", await _check_network()),
    ]
    table = Table("check", "status", "detail")
    failed = 0
    for name, (status, detail) in checks:
        color = StatusColor.get(status, "white")
        table.add_row(name, f"[{color}]{status}[/{color}]", detail)
        if status == "fail":
            failed += 1
    console.print(table)
    if failed:
        _fail(f"{failed} check(s) failed", code=1)
    console.print("[green]all checks passed[/green]")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def _fetch_pypi_version() -> tuple[str | None, str]:
    """Return (remote_version, note) for the ``intelxtract`` PyPI package."""
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://pypi.org/pypi/intelxtract/json") as resp:
                if resp.status == 404:
                    return (None, "not published")
                if resp.status != 200:
                    return (None, f"pypi returned HTTP {resp.status}")
                data = await resp.json()
                return (str(data["info"]["version"]), "ok")
    except Exception as exc:
        return (None, f"network error: {exc}")


@app.command()
def update() -> None:
    """Compare the installed version against PyPI (informational)."""
    asyncio.run(_update())


async def _update() -> None:
    remote, note = await _fetch_pypi_version()
    if remote is None and note == "not published":
        console.print(
            f"[yellow]IntelXtract {VERSION} is not published on PyPI yet.[/yellow]"
        )
        return
    if remote is None:
        console.print(f"[yellow]could not check PyPI:[/yellow] {note}")
        return
    if remote == VERSION:
        console.print(f"[green]up to date[/green] ({VERSION})")
    else:
        console.print(
            f"[yellow]update available:[/yellow] {remote} (installed: {VERSION})"
        )


__all__ = ["app"]
