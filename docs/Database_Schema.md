# Database Schema

Default engine: **SQLite** (via `aiosqlite`), file path from
`paths.db_path` (default `~/.local/share/intelxtract/intelxtract.db`).
PostgreSQL support is a post-1.0 option; the schema uses portable types
(`INTEGER`, `TEXT`, `REAL`) so it can be ported with minimal changes.

- Source of truth for DDL: [`database/schema.sql`](../database/schema.sql)
  (migration 1). Future changes ship as new forward-only migrations in
  `database/migrations.py` — applied migrations are never edited.
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
api_keys  (independent)       logs       (independent)
settings  (independent)
schema_version  (migration bookkeeping)
```

`ON DELETE CASCADE`: deleting a target removes its scans, findings, and
reports. `history.scan_id` uses `ON DELETE SET NULL` (entries survive scan
pruning).

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
| severity | TEXT | NULL | severity value (Phase 7+) |
| confidence | REAL | NULL, CHECK 0–1 | confidence (Phase 7+) |
| data | TEXT | NOT NULL | JSON payload |
| created_at | TEXT | NOT NULL | |

Indexes: `scan_id`, `(scan_id, module)`.

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
this table stores runtime/tool state (schedules, UI state) going forward.

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
