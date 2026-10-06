-- IntelXtract initial schema (migration 1).
-- Source of truth: docs/Database_Schema.md
-- Forward-only: never edit this file once applied; add a new migration.

CREATE TABLE IF NOT EXISTS targets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    value       TEXT    NOT NULL,
    type        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_targets_value_type
    ON targets (value, type);

CREATE TABLE IF NOT EXISTS scans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id   INTEGER NOT NULL REFERENCES targets (id) ON DELETE CASCADE,
    uuid        TEXT    NOT NULL,
    mode        TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    started_at  TEXT    NOT NULL,
    finished_at TEXT,
    duration    REAL    NOT NULL DEFAULT 0,
    error       TEXT,
    runs_json   TEXT    NOT NULL DEFAULT '[]',
    created_at  TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_uuid ON scans (uuid);
CREATE INDEX IF NOT EXISTS idx_scans_target ON scans (target_id);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans (status);

CREATE TABLE IF NOT EXISTS findings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id    INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    module     TEXT    NOT NULL,
    severity   TEXT,
    confidence REAL    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    data       TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings (scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_scan_module ON findings (scan_id, module);

CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id    INTEGER NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    path       TEXT    NOT NULL,
    format     TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_scan ON reports (scan_id);

CREATE TABLE IF NOT EXISTS plugins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    api_version INTEGER NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    description TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL,
    error       TEXT,
    updated_at  TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_plugins_name ON plugins (name);

CREATE TABLE IF NOT EXISTS api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT    NOT NULL,
    ciphertext  TEXT    NOT NULL,
    hint        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys (provider);

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT    NOT NULL,
    message    TEXT    NOT NULL,
    source     TEXT    NOT NULL DEFAULT '',
    context    TEXT    NOT NULL DEFAULT '{}',
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_level ON logs (level);
CREATE INDEX IF NOT EXISTS idx_logs_created ON logs (created_at);

CREATE TABLE IF NOT EXISTS history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id  INTEGER NOT NULL REFERENCES targets (id) ON DELETE CASCADE,
    scan_id    INTEGER REFERENCES scans (id) ON DELETE SET NULL,
    event_type TEXT    NOT NULL,
    payload    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_target_created
    ON history (target_id, created_at);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT    PRIMARY KEY,
    value      TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
