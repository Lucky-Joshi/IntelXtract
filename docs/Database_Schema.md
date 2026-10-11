# Database Schema

Default engine: **SQLite** (via `aiosqlite`), file path from
`paths.db_path` (default `~/.local/share/intelxtract/intelxtract.db`).
PostgreSQL support is a post-1.0 option; the schema uses portable types
(`INTEGER`, `TEXT`, `REAL`) so it can be ported with minimal changes.

- Source of truth for DDL: [`database/schema.sql`](../database/schema.sql)
  (migration 1). Future changes ship as new forward-only migrations in
  `database/migrations.py` — applied migrations are never edited.
  Migration 2 adds the normalized `findings.title`, `findings.evidence`,
  `findings.content_hash`, and `findings.collected_at` columns (Phase 7).
  Migration 3 adds the `schedules` table (Phase 21).
  Migration 4 adds the `cases`, `case_notes`, and `case_evidence` tables
  (Phase 22).
- All timestamps are **ISO-8601 UTC strings** (`2026-10-06T13:59:00+00:00`)
  except `duration` (REAL seconds) and confidence (REAL 0–1).
- JSON columns (`data`, `payload`, `context`, `value`, `runs_json`) hold
  UTF-8 JSON text.

## Relationships (ER diagram)

```text
targets 1 ────* scans 1 ────* findings
                 │ 1
                 ├────* reports
                 │ 0..1
history * ───────┘            plugins    (independent)
cases 1 ────* case_notes        case_evidence * ──── scans/findings (optional)
api_keys  (independent)       logs       (independent)
settings  (independent)
schema_version  (migration bookkeeping)
```

`ON DELETE CASCADE`: deleting a target removes its scans, findings, and
reports. `history.scan_id` uses `ON DELETE SET NULL` (entries survive scan
pruning). Deleting a case cascades its notes and evidence;
`case_evidence.scan_id`/`finding_id` use `ON DELETE SET NULL` so evidence
rows survive scan pruning.

## Tables

### targets

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | surrogate key |
| value | TEXT | NOT NULL | normalized target string |
| type | TEXT | NOT NULL | `TargetType` value (domain/ip/url/…) |
| created_at | TEXT | NOT NULL | first seen |

Indexes: `UNIQUE(value, type)`.

### scans

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | surrogate key (referenced by findings/reports/history) |
| target_id | INTEGER | NOT NULL, FK → targets(id) ON DELETE CASCADE | owner |
| uuid | TEXT | NOT NULL UNIQUE | engine `ScanResult.scan_id` |
| mode | TEXT | NOT NULL | quick/deep/custom |
| status | TEXT | NOT NULL | pending/running/completed/failed/cancelled |
| started_at | TEXT | NOT NULL | wall-clock start (UTC) |
| finished_at | TEXT | NULL | wall-clock end |
| duration | REAL | NOT NULL, default 0 | seconds |
| error | TEXT | NULL | scan-level failure |
| runs_json | TEXT | NOT NULL, default `'[]'` | serialized `ModuleRun[]` |
| created_at | TEXT | NOT NULL | row insert time |

Indexes: `uuid` UNIQUE, `target_id`, `status`.

> `runs_json` is a deliberate extension of the original plan table: module
> outcomes (success/failed/timeout/skipped with timings) are needed by
> reports and the dashboard, and normalizing them would require a
> `module_runs` table deferred until there is a query need.

### findings

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| scan_id | INTEGER | NOT NULL, FK → scans(id) ON DELETE CASCADE | owning scan |
| module | TEXT | NOT NULL | producing module name |
| title | TEXT | NOT NULL, default `''` | finding headline (migration 2, Phase 7) |
| severity | TEXT | NULL | severity level (`info`/`low`/`medium`/`high`/`critical`) |
| confidence | REAL | NULL, CHECK 0–1 | confidence of the finding |
| data | TEXT | NOT NULL | JSON payload |
| evidence | TEXT | NOT NULL, default `''` | supporting detail (migration 2, Phase 7) |
| content_hash | TEXT | NULL | SHA-256 dedupe key (migration 2, Phase 7) |
| collected_at | TEXT | NULL | when the module collected it (migration 2, Phase 7) |
| created_at | TEXT | NOT NULL | |

Indexes: `scan_id`, `(scan_id, module)`, `content_hash` (migration 2).

### reports

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| scan_id | INTEGER | NOT NULL, FK → scans(id) ON DELETE CASCADE | source scan |
| path | TEXT | NOT NULL | file path of the export |
| format | TEXT | NOT NULL | html/pdf/json/csv/md |
| created_at | TEXT | NOT NULL | |

Index: `scan_id`.

### plugins

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| name | TEXT | NOT NULL UNIQUE | plugin name |
| version | TEXT | NOT NULL | discovered version |
| api_version | INTEGER | NOT NULL | manifest API level |
| enabled | INTEGER | NOT NULL, CHECK in (0,1), default 1 | persisted toggle |
| description | TEXT | default `''` | |
| source | TEXT | NOT NULL | path to `plugin.py` |
| error | TEXT | NULL | last load error (fail-soft record) |
| updated_at | TEXT | NOT NULL | last discovery sync |

### api_keys

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| provider | TEXT | NOT NULL UNIQUE | e.g. virustotal |
| ciphertext | TEXT | NOT NULL | encrypted secret (plaintext never stored; encryption layer ships in Phase 24) |
| hint | TEXT | default `''` | masked display, e.g. `ab…yz` |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |

### logs

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| level | TEXT | NOT NULL | INFO/WARNING/… |
| message | TEXT | NOT NULL | redacted message |
| source | TEXT | default `''` | logger name |
| context | TEXT | default `'{}'` | JSON (scan_id, target, …) |
| created_at | TEXT | NOT NULL | |

Indexes: `level`, `created_at`.

### history

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| target_id | INTEGER | NOT NULL, FK → targets(id) ON DELETE CASCADE | |
| scan_id | INTEGER | NULL, FK → scans(id) ON DELETE SET NULL | related scan if any |
| event_type | TEXT | NOT NULL | e.g. `change`, `note`, `baseline` |
| payload | TEXT | NOT NULL | JSON details (diffs, milestones) |
| created_at | TEXT | NOT NULL | |

Indexes: `(target_id, created_at)`.

### settings

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| key | TEXT | PK | dotted or plain key |
| value | TEXT | NOT NULL | JSON-encoded value |
| updated_at | TEXT | NOT NULL | |

File-based `config/settings.json` remains the user configuration layer;
this table stores runtime/tool state (UI state) going forward.

### schedules

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| target | TEXT | NOT NULL | scan target |
| mode | TEXT | NOT NULL, default `quick` | scan profile |
| interval_seconds | INTEGER | NULL | fixed interval between runs |
| cron | TEXT | NULL | 5-field cron expression (alternative to interval) |
| enabled | INTEGER | NOT NULL, CHECK in (0,1), default 1 | scheduling toggle |
| status | TEXT | NOT NULL, default `idle` | `idle`/`running` (overlap guard) |
| last_run_at | TEXT | NULL | start of the last run |
| next_run_at | TEXT | NULL | when the schedule is next due |
| last_scan_id | INTEGER | NULL, FK → scans(id) ON DELETE SET NULL | most recent scan |
| last_error | TEXT | NULL | last run failure |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | |

Indexes: `next_run_at`, `(enabled, status)`.

> Migration 3 (Phase 21). A schedule defines exactly one cadence —
> `interval_seconds` or `cron`; the runner computes `next_run_at` after each
> run. Schedules stranded in `status = 'running'` are reset to `idle` on
> startup so interrupted scans are re-queued.

### cases

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| name | TEXT | NOT NULL | investigation name (unique) |
| description | TEXT | NOT NULL, default `''` | summary |
| status | TEXT | NOT NULL, default `open` | `open`/`closed`/… |
| created_at | TEXT | NOT NULL | |
| updated_at | TEXT | NOT NULL | bumped on note/evidence change |

Index: `name` UNIQUE.

### case_notes

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| case_id | INTEGER | NOT NULL, FK → cases(id) ON DELETE CASCADE | owner |
| body | TEXT | NOT NULL | note text |
| created_at | TEXT | NOT NULL | |

Index: `case_id`.

### case_evidence

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | INTEGER | PK AUTOINCREMENT | |
| case_id | INTEGER | NOT NULL, FK → cases(id) ON DELETE CASCADE | owner |
| scan_id | INTEGER | NULL, FK → scans(id) ON DELETE SET NULL | attached scan |
| finding_id | INTEGER | NULL, FK → findings(id) ON DELETE SET NULL | attached finding |
| kind | TEXT | NOT NULL, default `scan` | `scan`/`finding`/other |
| label | TEXT | NOT NULL, default `''` | human label |
| detail | TEXT | NOT NULL, default `''` | free-form detail |
| created_at | TEXT | NOT NULL | |

Indexes: `case_id`, `scan_id`.

> Migration 4 (Phase 22). A case groups scans, findings, notes, and evidence
> for one investigation; `collect_case_payload()` de-duplicates findings across
> attached scans/findings so a case exports as a single combined report.

### schema_version

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| version | INTEGER | PK | migration number |
| name | TEXT | NOT NULL | human label |
| applied_at | TEXT | NOT NULL | UTC timestamp |

## Conventions & rules

1. **Repositories own all SQL** — no ad-hoc queries outside
   `database/repositories.py`, `migrations.py`, and tests.
2. **Parameterized queries only** — string interpolation of values is
   forbidden (`docs/coding_standards.md`).
3. **Forward-only migrations** — never edit an applied migration; add the
   next numbered one.
4. **Indices follow query patterns** — every FK used in WHERE gets an index;
   composite indexes mirror the hot queries (per-scan findings, per-target
   history).
5. **Deletion story** — deleting a `targets` row cascades the case data it
   owns; `api_keys`/`plugins`/`settings` are independent configuration and
   are never cascade-deleted.
