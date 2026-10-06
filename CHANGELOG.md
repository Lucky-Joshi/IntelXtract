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

[Unreleased]: https://keepachangelog.com/en/1.1.0/
