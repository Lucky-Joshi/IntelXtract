# Changelog

All notable changes to IntelXtract are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Phase 0 — brand identity (`assets/logo.svg`, `assets/icon.svg`),
  `docs/brand/BRAND.md`, coding standards, git workflow, threat model, and
  privacy statement; folder architecture skeleton.
- Phase 1 — repository foundation: README, GPL-3.0 license, contributing and
  conduct documents, security policy, roadmap index, uv environment,
  Black/Ruff/Mypy/Pytest configuration, CI workflow, pre-commit hook, and
  smoke tests.
- Phase 2 — core architecture: constants and exception hierarchy, layered
  configuration, logging with secret redaction and scan-context binding,
  async TTL cache, async SQLite connection layer, fail-soft plugin loader,
  priority task scheduler, asyncio worker pool, scan engine facade, and
  unit tests for every component.
- Phase 3 — database layer: full schema (`targets`, `scans`, `findings`,
  `reports`, `plugins`, `api_keys`, `logs`, `history`, `settings`) with
  documented design in `docs/Database_Schema.md`, forward-only migration
  runner, typed repository layer with frozen record dataclasses, engine
  result-sink persistence, plugin metadata sync, and round-trip tests on
  temp databases. Engine scan timestamps now use wall clock for
  persistence.
- Phase 4 — CLI: Typer-based interface with `scan`, `report`, `history`,
  `config`, `plugin`, `doctor`, and `update` commands; `python -m cli` and
  `scripts/intelxtract` entry points; engine/worker-pool completion hooks
  (`on_module_done`, `on_task_done`); `ScanRepository.list`/`list_detailed`;
  SQLite connections now run in autocommit so writes survive process exit;
  CLI test suite via `typer.testing.CliRunner`.
- Phase 5 — GUI: PySide6 desktop shell with sidebar navigation and dark QSS
  theme from BRAND tokens; pages for Dashboard, Quick/Deep Scan (module
  checklist), Results, Reports, History, Plugins, API Manager, Settings, and
  About; `EngineBridge` running the asyncio engine on a worker `QThread` with
  queued Qt signals into the main thread; read-only SQLite sync helpers;
  `intelxtract-gui` entry point; offscreen smoke test suite
  (`QT_QPA_PLATFORM=offscreen`).
- Phase 6 — input engine: `core/input_engine.py` with a precedence-documented
  classifier (URL, email, IP v4/v6 with ports, hash md5/sha1/sha256, file
  path/dotfile/extension, domain with IDN→punycode, username, unknown);
  `parse_target`/`normalize` producing canonical `NormalizedTarget`
  (punycoded host, hex-lowercased hash, default URL scheme, compact IPv6)
  with actionable `ValidationError`s; `select_modules` selection map
  (quick/deep/custom profiles) now consumed by the scan planner with a
  fallback to all registered modules; the engine's default classifier now
  uses the real input engine instead of returning `unknown`; 87 table-driven
  classification/normalization/selection tests.

[Unreleased]: https://keepachangelog.com/en/1.1.0/
