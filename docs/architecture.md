# Architecture

This document describes the high-level system structure of IntelXtract as implemented through Phase 27. It reconciles and supersedes the earlier `internal_architecture.md` and `Scan_Engine_Workflow.md` documents.

## System Overview

```text
                                ┌─────────────────────┐
                                │  User Interfaces    │
                                │  ┌─────┐  ┌───────┐ │
                                │  │ CLI │  │  GUI  │ │
                                │  └──┬──┘  └───┬───┘ │
                                └─────┼────────┼─────┘
                                      │        │
                               ┌──────┴────────┴──────┐
                               │   Core Scan Engine   │
                               │  (core/engine.py)    │
                               │ ┌─────────────────┐  │
                               │ │ Input Engine    │  │  ← classify, normalize, select modules
                               │ │ (input_engine)  │  │
                               │ ├─────────────────┤  │
                               │ │ Scan Planner    │  │  ← module selection, key checks, validation
                               │ ├─────────────────┤  │
                               │ │ TaskScheduler   │  │  ← priority queue + state machine
                               │ │ (scheduler.py)  │  │
                               │ ├─────────────────┤  │
                               │ │ WorkerPool      │  │  ← bounded concurrency + timeouts
                               │ │ (worker_pool)   │  │
                               │ └────────┬────────┘  │
                               └──────────┼───────────┘
                                          │
               ┌──────────────────────────┼──────────────────────────┐
               ▼                          ▼                          ▼
    ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
    │   OSINT Modules     │    │  Plugin Modules     │    │  Shared Context     │
    │  (modules/*.py)     │    │  (plugins/*.py)     │    │  (ModuleContext)    │
    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │
    │ │ domain/dns      │ │    │ │ Wayback         │ │    │ │ HttpClient      │ │
    │ │ domain/whois    │ │    │ │ VirusTotal      │ │    │ │ AsyncTTLCache   │ │
    │ │ domain/ssl      │ │    │ │ (user plugins)  │ │    │ │ OffloadPool     │ │
    │ │ domain/subdomain│ │    │ └─────────────────┘ │    │ │ api_key()       │ │
    │ │ domain/http     │ │                        │    │ │ config.get()    │ │
    │ │ ip/geo          │ │                        │    │ │ cached()        │ │
    │ │ ip/rdns         │ │                        │    │ │ to_thread()     │ │
    │ │ ip/reputation   │ │                        │    │ └─────────────────┘ │
    │ │ email/collector │ │                        │    └─────────────────────┘
    │ │ username/...    │ │                        │
    │ │ website/...     │ │                        │
    │ │ certificate/... │ │                        │
    │ │ metadata/...    │ │                        │
    │ │ news/...        │ │                        │
    │ └─────────────────┘ │                        │
    └─────────────────────┘                        │
               │                                    │
               └──────────────┬─────────────────────┘
                              ▼
                   ┌───────────────────────┐
                   │  Correlation Engine   │
                   │  (core/correlation.py)│
                   │  NetworkX MultiDiGraph│
                   │  Entities + Edges     │
                   └───────────┬───────────┘
                               ▼
                   ┌───────────────────────┐
                   │    Risk Engine        │
                   │  (core/risk.py)       │
                   │  4 categories, ceilings│
                   │  30 deterministic rules│
                   └───────────┬───────────┘
                               ▼
                   ┌───────────────────────┐
                   │  Persistence Layer    │
                   │  (database/*.py)      │
                   │  SQLite + migrations  │
                   │  Repositories:        │
                   │  targets, scans,      │
                   │  findings, history,   │
                   │  plugins, schedules,  │
                   │  cases                │
                   └───────────┬───────────┘
                               ▼
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
      ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
      │ HTML Report │ │ PDF Report  │ │ JSON/CSV/MD │
      │ (Jinja2)    │ │ (WeasyPrint)│ │ exporters   │
      └─────────────┘ └─────────────┘ └─────────────┘
```

## Key Components

### 1. Input Engine (`core/input_engine.py`)

The entry point for every scan target. Responsibilities:

- **Classification** — Maps a raw string to `TargetType` (DOMAIN, IP, URL, EMAIL, USERNAME, HASH, FILE, UNKNOWN) using precedence rules (see docstring).
- **Normalization** — Produces a `NormalizedTarget` with canonical `value`, optional `port`, and `host`.
- **Module Selection** — `_QUICK_MODULES` and `_DEEP_MODULES` profiles per `TargetType` return the module name tuples for `ScanMode.QUICK`, `ScanMode.DEEP`, and `ScanMode.CUSTOM` (CUSTOM reuses DEEP; explicit module lists override).

### 2. Scan Engine (`core/engine.py`)

The orchestration facade. Public API:

```python
engine = ScanEngine(
    config,
    cache=AsyncTTLCache(...),
    modules=[...],           # ScanModule instances (core + plugins)
    classifier=classify,     # TargetType classifier
    result_sink=sink,        # async callable(ScanResult) -> None
    concurrency=8,
    timeout=30.0,
)
result = await engine.scan("example.com", mode=ScanMode.DEEP)
```

Internal flow (`ScanEngine.scan`):
1. Validate + classify target → `target_type`
2. `_plan()` — select modules via `input_engine.select_modules`, filter by `target_type`, check `requires_keys` against `api_keys.*`, run `module.validate(target)` → `(planned, skipped)`
3. Create `TaskScheduler`, submit each module's `run(target, ctx)` as a `Task`
4. Run `WorkerPool` with bounded concurrency; per-task timeout; completion hook fires `on_module_done`
5. Collect `ModuleRun` outcomes; extract `ModuleResult.findings`; deduplicate by `content_hash`
6. `build_graph(findings)` → correlation graph (NetworkX `MultiDiGraph`)
7. `assess_risk(findings)` → `RiskReport` (score 0–100, rating, categories, rule trace)
8. Persist via `result_sink` (if provided)
9. Return `ScanResult` with runs, findings, correlation, risk

### 3. Worker Pool (`core/worker_pool.py`)

- Bounded concurrency (`concurrency` workers)
- Sentinel-based shutdown
- Per-task timeout via `asyncio.wait_for`
- Isolates task failures; `on_task_done` callback fires per completion
- Returns `PoolStats` (submitted, done, failed, cancelled, duration, peak_in_flight)

### 4. Scheduler (`core/scheduler.py`)

- Priority queue (lower priority = runs first; FIFO tie-break)
- `Task` lifecycle: `PENDING → RUNNING → DONE/FAILED/CANCELLED`
- `mark_running`, `mark_done`, `mark_failed`, `mark_cancelled`, `cancel_pending`, `close_all`
- Counts per state; `submitted` total

### 5. Scheduled Scans (`core/scheduling.py`)

Three independent responsibilities:
- **Cadence math** — `compute_next_run(interval_seconds, cron, after)` supports fixed intervals and a 5-field cron subset (`CronExpression`)
- **Change detection** — `diff_findings(previous, current)` → `FindingDelta` (added/removed/changed keyed by `(module, title)`, signature by `content_hash`)
- **Runner** — `ScheduleRunner(ScheduleStore, run_scan)` polls due schedules, prevents overlap (`running` flag), advances `next_run_at`, recovers stranded runs

### 6. Module Context (`core/engine.py:ModuleContext`)

Everything a module needs during execution:

| Attribute / Method | Purpose |
|---|---|
| `config: Config` | Layered configuration lookup |
| `cache: AsyncTTLCache` | Shared TTL cache |
| `logger` | Structured logger |
| `scan_id: str` | Current scan UUID |
| `target_type: TargetType` | Classified target kind |
| `extras: dict` | Per-scan extra data |
| `http: HttpClient \| None` | Shared HTTP client (retries, pacing, ETag) |
| `offload: OffloadPool \| None` | Thread pool for blocking calls |
| `api_key(name: str) → str \| None` | Resolve `api_keys.<name>` from config |
| `get(key, default) → Any` | Read from `extras` |
| `to_thread(func, *args, **kwargs) → T` | Run blocking call off event loop |
| `cached(key, factory: Callable[[], Awaitable[T]], ttl?) → T` | Memoize async factory across scans |

### 7. Correlation Engine (`core/correlation.py`)

- Extracts entities from findings via `core.entities.EXTRACTORS` per module
- Builds deterministic `CorrelationGraph` (NetworkX `MultiDiGraph`)
- Nodes: entity `id` (stable `kind:hash`), `kind`, `value`, `count`
- Edges: typed (`resolves_to`, `registered_by`, `issued_to`, `same_email`, `part_of`, `mentions`, `profile`, `uses`) with `confidence`
- Applicators per module: DNS A/AAAA/CNAME, WHOIS registrar/email, SSL issuer/SAN, Certificate SAN/serial, Subdomain, News publisher, Tech stack, Username profile
- Cross-entity linking: email ↔ domain/username via `same_email`
- Output: `to_dict()` with `entities`, `edges`, `stats`

### 8. Risk Engine (`core/risk.py` + `core/risk_rules.py`)

Pure function `assess_risk(findings, target) → RiskReport`:

- 30 deterministic `RiskRule`s across 4 categories:
  - **TLS** (ceiling 40): cert expired (35), self-signed (18), no HTTPS (10)
  - **HEADERS** (ceiling 30): TRACE (15), HSTS (9), CSP (9), cookie Secure (7), X-Frame (4), Server (4), X-Content-Type (3), Referrer-Policy (2), cookie weak (2), Permissions-Policy (2)
  - **DNS** (ceiling 20): no DMARC (6), no SPF (4), DNSSEC absent (3), no MX (5), SPF +all (6), DMARC none (6)
  - **EXPOSURE** (ceiling 25): breach (20), GPS metadata (10), disposable email (4)
- Rules match on `module` + `title` substring + optional `when(finding)` predicate
- De-duplicated by `(rule_id, module, title, finding_key)`
- Category scores capped at ceilings; total capped at 100
- Rating bands: critical ≥75, high ≥50, medium ≥25, low <25
- Returns `RiskReport` with `score`, `rating`, `categories`, `rules[]`, `summary[]` (plain-language sentences)

### 9. Persistence (`database/persistence.py`)

Engine-agnostic `ResultSink = Callable[[ScanResult], Awaitable[None]]` implemented by `make_result_sink(db)`:

- `save_scan_result(db, result)` → scan id (writes target, scan, findings)
- `record_scan_change(repos, target_id, previous_scan_id, current_scan_id)` → `HistoryRecord` (baseline or change with `FindingDelta`)
- `collect_case_payload(repos, case)` → combined report model for case reports
- `sync_plugins(db, registry)` — upsert plugin metadata preserving enable flags

### 10. Plugin System (`core/plugin_loader.py`)

- Discovery: directories under `plugins/` containing `plugin.py` or `manifest.json`
- Fail-soft: broken plugins recorded with `error`, never crash app
- `PluginBase` abstract class with `name`, `version`, `api_version`, `target_types`, `requires_keys`, `validate(target)`, `run(target, ctx)`
- `PluginRegistry` → `discover()`, `apply_state()`, `enable()`, `disable()`, `engine_modules()` → `PluginModuleAdapter` (normalizes plugin output to `ModuleResult` via `parse_findings`)
- Manifest schema: `name`, `version`, `api_version` (≤ `PLUGIN_API_VERSION`), `author`, `description`, `entry_point`, `target_types[]`, `required_keys[]`

### 11. CLI (`cli/main.py`)

Typer app with sub-apps: `history`, `config`, `plugin`, `schedule`, `case`, `key`. Key commands:
- `scan target [--mode quick|deep|custom] [--modules csv] [--db PATH]`
- `report export <scan-ref> [--format json|csv|md|html|pdf] [--output FILE]`
- `history list|show|delete`
- `config get|set|list`
- `plugin list|info|enable|disable`
- `schedule add|list|remove|run`
- `case create|list|add-evidence|report`
- `key store|get|list|delete`
- `doctor` — health check (DB, vault, config, modules, network)
- `serve` — run schedule runner foreground

### 12. GUI (`gui/main_window.py` + `gui/pages/*`)

PySide6 application with sidebar navigation (13 pages):
- Dashboard — overview, recent scans, quick actions
- Quick Scan / Deep Scan — target input, mode selection, live progress
- Results — findings table, severity filter, evidence, correlation graph
- Reports — list, preview, export (HTML/PDF/JSON/CSV/MD)
- History — scan list, search, diff
- Cases — create, attach scans/findings, combined report
- Schedules — add/edit/remove, cron/interval, run now
- Assistant — AI chat (local/remote LLM) with scan context
- Plugins — list, enable/disable, info
- API Manager — configure `api_keys.*`
- Settings — config editor, theme, paths
- About — version, links

Bridge: `EngineBridge(QObject)` runs `ScanEngine` on a `QThread` with dedicated asyncio loop; signals: `scan_started`, `module_finished(dict)`, `scan_finished(dict)`, `scan_failed(str)`, `modules_ready(list[str])`.

### 13. Reporting (`reports/builder.py` + `reports/exporter.py`)

- `build_report(scan, target, findings) → ReportModel` — re-derives correlation + risk from findings so persisted scans work
- `ReportModel`: generated_at, app, scan, target, findings, correlation, risk, severity_counts, module_counts, timeline (news), executive_summary, evidence_refs, methodology
- Exporters: JSON (`.json`), CSV (`.csv`), Markdown (`.md`), HTML (`.html` via Jinja2 + `brand_tokens`), PDF (`.pdf` via WeasyPrint; falls back to print-friendly HTML with warning)

---

## Data Flow Summary

```
User Input (CLI/GUI)
       │
       ▼
┌──────────────────┐
│ Input Engine     │  classify() → TargetType
│                  │  normalize() → NormalizedTarget
│                  │  select_modules() → module names
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ScanEngine.scan  │  _plan() → (planned modules, skipped runs)
│                  │  TaskScheduler.submit(module.run(target, ctx))
│                  │  WorkerPool.run() → ModuleRun[]
│                  │  _build_result() → findings (deduped by content_hash)
│                  │  build_graph() → CorrelationGraph
│                  │  assess_risk() → RiskReport
│                  │  result_sink() → DB
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ScanResult       │  scan_id, target, target_type, mode, status,
│                  │  started_at, finished_at, runs[], findings[],
│                  │  correlation{}, risk{}, error
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
Persistence  Report Export
    │
    ▼
┌──────────────────┐
│ SQLite DB        │  targets, scans, findings, history, plugins,
│                  │  schedules, cases
└──────────────────┘
```

---

## Design Principles

1. **Fail-soft everywhere** — module failures never fail the scan; plugin load errors never crash startup; risk/correlation exceptions are caught and logged.
2. **Deterministic output** — same findings → same correlation graph, same risk score, same report bytes.
3. **Separation of concerns** — engine knows nothing about DB, UI, or network; modules receive only `ModuleContext`; persistence is a sink.
4. **Profile-driven module selection** — QUICK/DEEP/CUSTOM maps in `input_engine.py`; registry `select()` intersects with enabled modules.
5. **Key-gated modules** — `requires_keys` checked in planner; missing keys → `SKIPPED` (not an error).
6. **Offload for blocking work** — `ctx.to_thread()` uses per-scan `OffloadPool`; `ctx.cached()` memoizes async factories.
7. **Async-first** — all I/O via `HttpClient` (pooled connector, retries, pacing, ETag); `WorkerPool` uses native asyncio.