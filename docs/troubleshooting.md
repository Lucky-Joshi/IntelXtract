# Troubleshooting Guide

## Quick Diagnostic

Run the built-in health check:

```bash
intelxtract doctor
```

Checks: database, vault, config, module discovery, network reachability.

---

## Database Issues

### `database is locked`

**Cause**: Multiple processes writing to the same SQLite file.

**Fix**:
- Ensure only one `intelxtract` process uses the DB at a time
- Check `paths.db_path` in config — each user/project should have its own
- For concurrent access, consider PostgreSQL (not yet implemented)

### `migration failed` / `schema version mismatch`

**Cause**: Database schema version doesn't match code expectations.

**Fix**:
```bash
# Development only — destroys data
intelxtract db migrate --force

# Production: backup first, then check migrations in database/migrations.py
```

### `no such table: plugins` (or other missing tables)

**Cause**: Migrations haven't run.

**Fix**:
```bash
intelxtract doctor
# If it reports migration issues:
intelxtract scan example.com  # Triggers migration on DB open
```

---

## Vault / API Key Issues

### `VaultError: invalid key` / `decryption failed`

**Cause**: Vault master key changed or corrupted.

**Fix**:
```bash
# List stored keys (shows masked values)
intelxtract key list

# Re-store the problematic key
intelxtract key store virustotal NEW_API_KEY
```

### Module shows `SKIPPED: missing api key`

**Cause**: Module declares `requires_keys = ("name",)` but `api_keys.name` not set.

**Fix**:
```bash
intelxtract key store name YOUR_API_KEY
intelxtract key list  # Verify it's stored
```

---

## Module / Scan Issues

### `ScanEngine: module discovery failed`

**Cause**: Import error in `modules/` package.

**Debug**:
```bash
python -c "from modules.registry import ModuleRegistry; r = ModuleRegistry(packages=['modules.domain']); print(r.names())"
```

Check the traceback — usually a missing dependency or syntax error in a module file.

### Module not running for my target

**Checklist**:
1. Target classified correctly? `intelxtract scan example.com --json | jq .target_type`
2. Module in the selected profile? Check `core/input_engine.py` `_QUICK_MODULES` / `_DEEP_MODULES`
3. Module enabled? `intelxtract plugin list` (for plugins) or registry `is_enabled()`
4. `requires_keys` satisfied? See vault section above
5. `module.validate(target)` passing? Add debug logging to your module

### Scan hangs / times out

**Causes & Fixes**:
- **Slow network**: Increase `scan.default_timeout` (default 30s) or `network.request_timeout`
- **Module deadlock**: Ensure all `await` calls use `ctx.http` (has timeouts) not raw `aiohttp`
- **Worker pool starvation**: Check `scan.max_workers` (default 8); modules should be async

### `content_hash` collisions / duplicate findings

**Cause**: Two findings have identical `module`, `title`, `severity`, `data`, `evidence`.

**Fix**: This is expected deduplication behavior. If you need distinct findings, differentiate `title` or include unique data in `data`.

---

## Network / HTTP Issues

### `aiohttp.ClientConnectorError` / `Cannot connect to host`

**Cause**: DNS resolution failed, host unreachable, or firewall.

**Fix**:
- Check target is correct and reachable from your network
- Verify proxy settings if behind corporate firewall (not yet configurable — use system proxy env vars)
- For offline testing: use the integration test mock server pattern

### `asyncio.TimeoutError` in HTTP requests

**Cause**: Request exceeded `network.request_timeout` (default 10s) or per-host pacing.

**Fix**:
```toml
# config.toml
network.request_timeout = 30.0
network.per_host_limit = 5  # Reduce if hitting rate limits
```

### SSL / Certificate verification errors

**Cause**: Target uses self-signed or expired cert; or system CA bundle outdated.

**Fix**:
- For testing: `ctx.http.get_json(url, ssl=False)` (not exposed directly — would need module change)
- Update system CA certificates: `sudo update-ca-certificates` (Debian/Ubuntu) or `sudo yum install ca-certificates` (RHEL)

---

## GUI Issues

### GUI won't start / blank window

**Check**:
```bash
# Verbose Qt plugin debug
QT_DEBUG_PLUGINS=1 python -m gui.main
```

**Common fixes**:
- Install system Qt6: `apt install qt6-base` (Ubuntu/Debian), `brew install qt6` (macOS)
- Ensure `PySide6==6.10.3` is installed in venv
- On Wayland: try `QT_QPA_PLATFORM=xcb python -m gui.main`

### `ModuleNotFoundError: No module named 'gui.pages.*'`

**Cause**: Running from wrong directory or PYTHONPATH issue.

**Fix**:
```bash
cd /path/to/IntelXtract
python -m gui.main
```

### High CPU / memory in GUI

**Cause**: Correlation graph with many nodes, or frequent scan progress updates.

**Fix**:
- Reduce `scan.max_workers` for large scans
- Close unused tabs (Results graph, Timeline)
- Restart GUI to clear accumulated state

---

## Report Export Issues

### PDF export falls back to HTML with warning

**Cause**: WeasyPrint not installed or missing system dependencies.

**Fix**:
```bash
# Install WeasyPrint + system deps (Ubuntu/Debian)
sudo apt install python3-dev libpango-1.0-0 libharfbuzz0b libpangocairo-1.0-0
uv pip install weasyprint

# macOS
brew install pango cairo gdk-pixbuf libffi
uv pip install weasyprint
```

### Report missing correlation / risk sections

**Cause**: Scan completed before Phase 16/17, or correlation/risk raised exceptions.

**Fix**: Re-run the scan — `build_report` re-derives correlation and risk from findings deterministically.

---

## Scheduled Scan Issues

### Schedules not running

**Checklist**:
1. Scheduler running? `intelxtract serve` or `intelxtract schedule run`
2. Schedule due? `intelxtract schedule list` — check `next_run_at`
3. Schedule enabled? (no disable flag in current schema — remove and re-add)
4. Database accessible? `intelxtract doctor`

### `ScheduleRunner` overlapping runs

**Cause**: Previous run hasn't finished when next tick fires.

**Fix**: The runner prevents overlap via `running` flag in DB. If stuck:
```bash
# Reset stuck schedules (dev only)
sqlite3 ~/.local/share/intelxtract/intelxtract.db "UPDATE schedules SET status='idle' WHERE status='running';"
```

---

## Performance Issues

### High memory usage during scans

**Causes**:
- Large `AsyncTTLCache` (`cache.max_size`, default 1024 entries)
- Many findings retained in memory

**Fix**:
```toml
cache.max_size = 512
cache.ttl = 180
```

### Slow scan startup

**Cause**: Module discovery importing all packages.

**Fix**: Module registry caches instances; subsequent scans are faster. For CLI, this is per-invocation overhead.

---

## Test Failures

### `mypy: Duplicate module named "conftest"`

**Cause**: Multiple `conftest.py` files without `__init__.py` in parent directories.

**Fix**: Don't add `conftest.py` under `tests/integration/` or `tests/gui/` — define fixtures inside test modules instead.

### `ruff: S608` (f-string SQL)

**Cause**: Raw SQL with f-strings in tests.

**Fix**: Add `# noqa: S608` comment on the line, or use parameterized queries.

### `mypy: target_types tuple[TargetType] vs tuple[TargetType, ...]`

**Cause**: Protocol expects `tuple[TargetType, ...]`; concrete modules declare `target_types = (TargetType.DOMAIN,)`.

**Fix**: In tests, annotate `modules: list[Any] = [...]` before passing to `ScanEngine`. Production code uses `list[Any]` for module lists.

### `pytest-qt` `qapp` fixture conflict

**Cause**: Local `tests/gui/conftest.py` defines session-scoped `qapp` that shadows pytest-qt's.

**Fix**: Use `qtbot` fixture (works correctly) — the shadowed `qapp` is harmless.

---

## Getting Help

1. Run `intelxtract doctor` and include output
2. Check `docs/troubleshooting.md` for your symptom
3. Search existing issues on GitHub
4. Open a new issue with:
   - Command that failed
   - Full error traceback
   - `intelxtract doctor` output
   - Python version (`python --version`)
   - OS / distribution

---

## Logs

Enable debug logging:

```bash
# CLI
INTELXTRACT_LOG_LEVEL=DEBUG intelxtract scan example.com

# GUI
INTELXTRACT_LOG_LEVEL=DEBUG python -m gui.main
```

Logs go to stderr by default; configure file output in `core/logger.py` or via config.