
### Phase 29 — Version 1.0 Release

- **Release checklist (S29.1)**: Full verification pass — CLI/GUI stable, all 12 core module categories functional, 5 report formats working, 2 reference plugins (Wayback, VirusTotal) operational, 756 tests passing, 89.5% branch coverage, `doctor` all green, deep scan + HTML/PDF reports confirmed.
- **CI/CD release workflow (S29.2)**: `.github/workflows/release.yml` — on tag push (`v*`), runs quality gate, builds wheel/sdist, PyInstaller CLI/GUI binaries, Docker images, generates SHA256/SHA512 checksums, creates draft GitHub Release with all artifacts and auto-generated notes.
- **Community files (S29.3)**: `.github/ISSUE_TEMPLATE/` — bug_report.yml, feature_request.yml, module_request.yml; `.github/PULL_REQUEST_TEMPLATE.md` with phase/sub-phase checklist; `CODEOWNERS` mapping 15+ ownership areas to teams.
- **Example reports (S29.4)**: `examples/` — quick/deep scan reports in JSON/HTML/MD/CSV, case investigation report combining 2 scans (66 findings), README with generation instructions.
- **Release notes (S29.5)**: This entry; migration notes (schema v1→v4 auto-migration, no manual steps); known limitations (PDF needs WeasyPrint system deps, GUI needs Qt6 libs, no REST API yet, no batch scan CLI); ethical-use statement reaffirmed (passive OSINT only, no exploitation).
- **Tag**: `v1.0.0` (created locally; push is user-owned).

### Phase 28 — Packaging

- PyPI metadata: `pyproject.toml` gains full `[project]` table (name, version, description, dependencies, entry points, classifiers, URLs) with SPDX license and `project.entry-points.console_scripts` for `intelxtract` and `intelxtract-gui`; `tool.setuptools.packages.find` configured for flat-layout package discovery (S28.3).
- `python -m build --wheel --sdist` succeeds producing `intelxtract-0.1.0a0-py3-none-any.whl` and `intelxtract-0.1.0a0.tar.gz`; editable install works and CLI entry points resolve (S28.3).
- PyInstaller spec files: `scripts/pyinstaller/intelxtract-cli.spec` and `intelxtract-gui.spec` with comprehensive hidden imports, data bundling (assets, templates, schema.sql, plugins), UPX compression, and platform-appropriate excludes; CLI binary builds and smoke-tests (`intelxtract scan example.com --mode quick --format json` completes in ~0.3s) (S28.1).
- Docker: multi-stage `Dockerfile` with builder/runtime/gui targets; `runtime` target is minimal headless CLI (~150MB); `gui` target adds Qt6 dependencies; `docker-compose.yml` defines `intelxtract`, `intelxtract-gui`, and `intelxtract-scheduler` services with named volumes for data/config/plugins (S28.2).
- Build scripts: `scripts/build.sh` (Linux/macOS) and `scripts/build.ps1` (Windows) support `--clean`, `--cli-only`, `--gui-only`, `--wheel`, `--docker`, `--verbose`; generate `CHECKSUMS.sha256` and `CHECKSUMS.sha512` for all artifacts (S28.4).
- `database/migrations.py` uses `importlib.resources.read_text` for schema.sql so it works in both source and PyInstaller-frozen environments.

### Phase 27 — Documentation

- Architecture reconciled: `docs/architecture.md` rewritten as single source of truth (supersedes `internal_architecture.md` and `Scan_Engine_Workflow.md`) with complete system diagram, component descriptions, data flow, and design principles (S27.1).
- `docs/user_guide.md` (new) — complete installation guide, CLI cookbook with all commands/examples, GUI walkthrough with 13-page breakdown, scan mode deep dive, module reference table, report format specs (S27.2).
- `docs/developer_guide.md` (new) — module authoring guide (6-step process with code template), test conventions (fixtures, patterns, GUI/integration/perf), code conventions (typing, async, errors, naming, security), phase-gate workflow, common commands (S27.3).
- `docs/plugin_sdk.md` finalized with verbatim `manifest.json` and `plugin.py` for the three reference plugins (`Wayback`, `VirusTotal`, `_template`), context API table, testing patterns, versioning, best practices (S27.4).
- `docs/faq.md` (new) — 30+ Q&A covering general, install, config, scanning, reports, schedules, plugins, GUI, development (S27.5).
- `docs/troubleshooting.md` (new) — diagnostic sections for database, vault, modules, network, GUI, reports, schedules, performance, test failures with causes and fixes (S27.5).
- `README.md` polished: quickstart, badges (Python, License, Phase, Tests, Coverage), full feature matrix table with status checkmarks, updated architecture diagram, documentation index (S27.6).

### Phase 26 — Testing

- Coverage tooling: `pytest-cov` + `pytest-qt` added to `requirements-dev.txt`; `pyproject.toml` gains `[tool.coverage.run]` (branch coverage over `core`/`modules`/`reports`/`plugins`) and `[tool.coverage.report]` (`fail_under = 80`, missing lines, standard exclusions); CI now runs `pytest -m "not integration" --cov --cov-report=term --cov-report=html:htmlcov` so the coverage floor is enforced on every push (S26.1/S26.8).
- Unit coverage is **89.5%** overall (756 tests, branch coverage) — comfortably above the 80% floor, with the whole offline suite running in ~9s locally (S26.2).
- `tests/integration/test_offline_scan.py` (new) — end-to-end scans (`ScanEngine` → shared `HttpClient` → real aiohttp transport → domain/IP collectors) against an in-process loopback mock serving DoH-JSON, RDAP, crt.sh, and ip-api shapes; asserts module success, parsed findings, and persistence through the DB sink, with no external network (S26.3).
- `tests/cli/test_cli.py` — full command matrix: every top-level command and nested subcommand (`history`/`config`/`plugin`/`schedule`/`case`/`key`) is registered and its `--help` exits 0, plus a registry-completeness check that guards against forgotten registrations (S26.4).
- `tests/gui/test_qtbot.py` (new) — `pytest-qt` (`qtbot`) offscreen tests for sidebar page navigation and a quick-scan start that renders into the results page; the existing session-scoped offscreen `qapp` fixture continues to back `qtbot` (S26.5).
- `tests/database/test_migrations.py` — upgrade from **every released schema version** (v1→v4, v2→v4, v3→v4) with data-preservation assertions, plus idempotent re-upgrade over a head database; `tests/core/test_plugin_loader.py` gains syntax-error and `None`-result adapter failure-mode coverage (S26.6).
- `tests/core/test_performance_budget.py` (new) — generous wall-clock budget assertions on the warm cache path (200k ops), the scan+dedupe pipeline (300 scans), and `ctx.cached` memoization (S26.7).

### Phase 25 — Performance

- `core/http_client.py` — one lazily-created keep-alive `aiohttp.TCPConnector` per client with total/per-host connection caps and a DNS cache (`network.pool_limit`, `network.pool_limit_per_host`), closed on `aclose()` (S25.1).
- `core/http_client.py` — conditional-request caching: GET responses that carry `ETag`/`Last-Modified` are stored in the engine's shared `AsyncTTLCache` and revalidated with `If-None-Match`/`If-Modified-Since`, serving the cached body on `304` for `fetch`/`request`/`get_json`; `network.http_cache` toggles it (S25.2).
- `core/engine.py` — `ScanEngine` passes its shared cache into the per-scan `HttpClient`, and `ModuleContext.cached()` provides get-or-compute module result caching with TTL (S25.2).
- `core/http_client.py` — retry backoff is now exponential with equal jitter capped at `network.backoff_max` (replacing `0.5 * (attempt + 1)`); only idempotent methods (GET/HEAD/OPTIONS/PUT/DELETE) retry on 408/429/5xx while transient network errors still retry within `network.retries` (S25.3).
- `core/offload.py` (new) — `OffloadPool` (bounded `ThreadPoolExecutor`), a process-wide `offload()` helper, and `configure_offload`/`shutdown_offload`; `performance.offload_workers` bounds the per-scan pool (S25.4).
- Metadata extraction (PDF/EXIF/OOXML) and the username site-registry load now run off the event loop via `ModuleContext.to_thread()`; a slow-task probe test asserts the loop stays responsive (S25.4).
- `core/http_client.py` — global (`network.max_concurrency`) and per-host (`network.max_per_host`) in-flight semaphores plus `network.rate_limit_per_host` per-provider pacing beside the existing global pacing (S25.5).
- `scripts/bench.py` (new) — offline benchmarks for cache throughput, scan throughput, and offload throughput (`--quick`/`--json`); baseline numbers recorded in `docs/performance.md` (S25.6).
- Docs/tests: `docs/performance.md`, new `network.*`/`performance.*` defaults and `.env.example` entries; tests for offload responsiveness/bounding, connector build, backoff bounds/growth/idempotency gating, concurrency caps, per-host pacing, `304` cache serving, engine offload pool + `ctx.cached`, module off-thread extraction, and benchmark smoke tests.

### Phase 24 — Settings

- `core/vault.py` — new Fernet-backed API-key vault (S24.1). Key material resolves `INTELXTRACT_VAULT_KEY` → OS `keyring` (optional) → a `0600` key file at `vault.key_path`; `store_key`/`get_key`/`delete_key`/`list_stored` keep ciphertext + masked hint in the existing `api_keys` table, and `hydrate_api_keys` decrypts stored secrets into config (env/`.env` always wins) while migrating any legacy plaintext keys out of `settings.json`.
- `core/config.py` — new `vault` and `gui` sections plus `app.telemetry` (always `false`) and `network.proxy`/`network.rate_limit`; `Config.env_keys()` records which dotted keys came from the environment; `Config.save()` never writes the `api_keys` section so hydrated secrets cannot leak back to disk (S24.1/S24.3).
- `core/http_client.py` — `HttpClient` now consumes `network.proxy` (per-request `proxy=`) and `network.rate_limit` (async request pacing), and reads `network.timeout`/`network.retries` (with legacy `http.*` fallback) (S24.2).
- `core/cache.py` — `AsyncTTLCache(enabled=False)` makes the response cache an explicit no-op; `ScanEngine` wires it from `cache.enabled` (S24.3).
- CLI — `key set|get|list|delete` (`--reveal`, `--yes`) for the encrypted vault; `config set api_keys.*` is rejected with a pointer to `key set`, and `config list` masks `api_keys.*` (S24.1).
- GUI — API Manager rewritten to store through the vault (no plaintext banner/behavior), Settings page gains theme/language, proxy, rate limit, network timeout/retries, cache toggle, and log-rotation fields, and `create_window` hydrates the vault (S24.4).
- Docs/tests: vault round-trip/ciphertext/0600 perms/keyring+file+env key resolution/delete/legacy-migration/precedence (env > vault > config file > defaults), `save()` secret-stripping, HTTP proxy/rate-limit, disabled-cache, and CLI key lifecycle (684 passed).

### Phase 23 — AI Assistant (optional)

- `assistant/providers.py` — `AssistantProvider` Protocol + `ChatMessage`/`AssistantResponse`; `DisabledAssistant` (inert default, makes no network call) and `OpenAICompatibleAssistant` (any OpenAI-compatible `/chat/completions` endpoint, user-supplied URL/model/key) built by `build_provider()` (S23.1).
- `core/config.py` — new `assistant` section (`enabled=false`, `provider=disabled`, `base_url`, `model`, `api_key`, `timeout`, `max_tokens`, `temperature`); `assistant.enabled` must be true before anything is sent (S23.1).
- `core/http_client.py` — `HttpClient.post_json()` (JSON body + auth headers, raises on 4xx/5xx) powers the provider; `core/exceptions.py` gains `AssistantError` (S23.1).
- `assistant/prompts.py` — one guardrail system prompt ("use only the supplied evidence… do not invent… say when insufficient… never present AI text as a finding") shared by summarize / explain / compare / next-steps templates that embed the report model (target, risk, findings, raw evidence, timeline) as JSON (S23.2).
- `assistant/service.py` — `Assistant` facade (`summarize`, `suggest_next_steps`, `explain`, `compare`, `ask`) returning `AssistantAnswer` (text, provider, model, `label="AI-generated"`, warning); disabled/error/empty paths return safe labeled answers (S23.2/S23.3).
- CLI — `explain <scan>` (`--kind summary|next-steps|finding|compare`, `--finding`, `--compare`, `--json`); disabled by default with a clear stderr notice and exit 1; output prints an AI-generated banner and provider/model line (S23.3).
- GUI — Assistant page (scan id + kind, Ask, labeled read-only output, disabled banner); provider runs off the UI thread; registered in the sidebar (S23.3).
- Tests: provider disabled/credential-gating/unknown-provider/parse/empty-content, prompt assembly + guardrail, service disable/error/empty/dispatch, CLI summary/json/finding/compare/disabled/errors, GUI AssistantPage disabled + mocked-provider round-trip (657 passed).

### Phase 22 — Case Management

- `database/migrations.py` — migration 4 creates `cases` (unique name, status, timestamps), `case_notes`, and `case_evidence` (`scan_id`/`finding_id` → scans/findings `ON DELETE SET NULL`) with per-case/scan indexes (S22.1).
- `database/repositories.py` — `CaseRecord`/`CaseNoteRecord`/`CaseEvidenceRecord` + `CaseRepository` (`create`, `get`, `get_by_name`, `resolve`, `set_status`, `delete`, `list`, `add_note`, `list_notes`, `attach`, `list_evidence`) wired into `Repositories`; `FindingRepository.get` added for direct finding attachment (S22.1/S22.2).
- `database/persistence.py` — `collect_case_payload()` gathers notes, evidence, and the de-duplicated union of findings from every attached scan/finding (reports reuse `build_report`, so a case exports as one combined report) (S22.2).
- CLI — `case create|list|show|note|attach|export`; `export` writes `json|html|csv|md|pdf` to `exports/case-<id>.<ext>` or `--out` with PDF-fallback warnings (S22.2).
- GUI — `gui/case_sync.py` (read + write sqlite helpers) and a Cases page (create case, add notes, attach scan ids, view combined findings); registered in the sidebar (S22.3).
- Tests: migration version/table updates; `CaseRepository` CRUD/duplicate/unknown/cascade/notes/evidence/payload round-trips; CLI create/list/show/note/attach/export; GUI cases-page create→note→attach→duplicate (S22.4).

### Phase 21 — Scheduler

- `database/migrations.py` — migration 3 creates the `schedules` table (target, mode, `interval_seconds`/`cron`, enabled, status, last/next run, last scan/error, timestamps) with `next_run`/`enabled` indexes (S21.1).
- `database/repositories.py` — `ScheduleRecord` + `ScheduleRepository` (`create`, `get`, `due`, `set_enabled`, `mark_running`, `mark_finished`, `reset_running`, `delete`, `list`) wired into `Repositories` (S21.1).
- `core/scheduling.py` — `CronExpression` (5-field subset incl. steps/lists/ranges, crontab day-OR-weekday semantics), `compute_next_run`/`validate_cadence`, `FindingDelta`/`diff_findings` (`(module, title)`-keyed added/removed/changed), and `ScheduleRunner` (due-draining poll loop, in-flight overlap prevention, `recover()` of stranded runs, next-run advancement) behind a Protocol store so core stays DB-free (S21.2/S21.3).
- `database/persistence.py` — `record_scan_change()` writes `baseline`/`change` `history` events payloaded with `{previous_scan_id, current_scan_id, added, removed, changed, counts}` (S21.3).
- CLI — `schedule add|list|remove|enable|disable|run` (`--every`/`--cron`, `--once`/`--iterations`/`--poll`) drives the real engine and records change history (S21.4).
- GUI — `db_sync.list_schedules()` + read-only Schedules page added to the sidebar (S21.4).
- Tests: cron parsing/next-run edge cases, interval cadence, diff correctness, runner with fake clock/store (due triggering, error capture, overlap, `recover`, stop), `ScheduleRepository` CRUD/due/reset, change-history round-trip, and CLI add/list/toggle/remove/run-once (604 passed).

### Phase 20 — Plugin SDK

- `core/plugin_loader.py` — `MANIFEST_SCHEMA` + `validate_manifest()` (typed schema check with fail-soft reporting); manifests are now overrides with type/format validation, unknown keys tolerated for forward compatibility.
- Manifest-driven discovery: `entry_point` selects the module to import (default `plugin.py`, must stay inside the plugin dir); registry now keys plugins by resolved name; new `author` / `required_keys` metadata on `PluginInfo`; `required_keys` gate is honored by the engine planner.
- `PluginModuleAdapter` + `PluginRegistry.engine_modules()` — plugins run through the same `ScanEngine` pipeline as core modules; adapter normalizes any plugin return value into a `ModuleResult` (mappings → `data`, title-shaped content → findings).
- `PluginRegistry.apply_state()` hydrates persisted enable/disable flags; CLI `plugin list` applies DB state before rendering.
- Example plugins: `plugins/Wayback/` (Web Archive CDX history, key-free) and `plugins/VirusTotal/` (key-gated `required_keys=["virustotal"]` reputation report) as living references.
- `docs/plugin_sdk.md` + `plugins/_template/` (manifest, plugin, README) cookiecutter-style starter.
- Tests: manifest validation (accept/type errors/fail-soft), `entry_point` resolution, name-keyed registry, `apply_state`, adapter normalization + context use, engine-pipeline run of the Wayback plugin with a fake HTTP client, VirusTotal key gating and detection grading, offline/failure handling (561 passed).

### Phase 19 — Reporting

- `reports/brand.py` — brand tokens parsed from `BRAND.md` (accent, page/card background, text, muted, border) with defaults; `BRAND.md` added at repo root as the visual source of truth (S19.2).
- `reports/builder.py` — shared `ReportModel`: executive summary, severity counts, module counts, timeline, evidence refs (top-EVIDENCE_LIMIT, critical-first), methodology; deterministically re-derives correlation (`TargetType`-coerced) and risk from findings so persisted pre-P16/P17 scans still get full reports; fixed `generated_at` support for stable snapshots.
- `reports/exporter.py` — `export_report()` for `json|html|csv|md|pdf`: JSON = canonical model, CSV = one row per finding (critical-first), Markdown = one-file report, HTML = Jinja2 template rendered from brand tokens, PDF = WeasyPrint when its system libraries exist, otherwise a print-friendly HTML fallback with an explicit warning (never fails).
- `templates/report.html.j2` — single template with an on-screen styled mode and a print-mode CSS switching to plain black-on-white; sections: brand header, executive summary, risk overview with per-category bars + rule trace, severity-grouped findings table, module counts, timeline, methodology/evidence, timestamped footer.
- `cli/report` — replaced the JSON stub: every format (`--format`) writes bytes to `exports/report-<id>.<ext>` or `--out`, prints format/fallback warnings, and registers the report in the `reports` table (S19.5).
- `gui/pages/reports.py` — points users at the CLI formats instead of implying later GUI-only generation.
- Tests: golden JSON snapshot (`tests/reports/golden/report.json`), model section/ordering tests, determinism, CSV row counts incl. empty case, Markdown sections, HTML brand/section markers, PDF fallback (WeasyPrint absent) + fake-weasyprint byte path, unsupported-format raise, CLI JSON round-trip + parametrized format loop + PDF-fallback file/warning checks.

### Phase 16 — Correlation Engine

- `core/entities.py` — stable entity model (10 kinds, normalized value hash IDs) + per-module extractors over `Finding.data`.
- `core/correlation.py` — NetworkX MultiDiGraph linker: `resolves_to`, `registered_by`, `issued_to`, `same_email`, `part_of`, `mentions`, `profile`, `uses` edges with confidence.
- `ScanResult.correlation` — deterministic graph JSON (entities/edges/stats) computed at scan end; included in `to_dict`/exports, never fails a scan.
- `requirements.txt`: pin `networkx==3.7`.
- 9 new tests (entity normalization/ids, extractor aggregation, expected edge set, connected components, cross-scan determinism, empty-findings).


### Phase 17 — Risk Engine

- `core/risk_rules.py` — documented rule table (module + title pattern → category + weight): expired/self-signed TLS, no HTTPS, TRACE, missing HSTS/CSP/XFO/XCTO/Referrer/Permissions, server disclosure, insecure cookies, missing/weak SPF + DMARC + MX, absent DNSSEC, breach exposure, GPS metadata, disposable email.
- `core/risk.py` — pure `assess_risk()` scoring: category sub-scores (TLS/HEADERS/DNS/EXPOSURE) with documented ceilings, 0-100 score → `low|medium|high|critical`, deterministic de-duped/ordered rule trace, plain-language top-risk summary.
- `ScanResult.risk` — computed at scan end from flattened findings, included in `to_dict()`/exports, guarded so it never fails a scan.
- 10 new tests: rating bands, golden scores, category ceilings, 100-cap saturation, cookie flag weights, weak SPF/DMARC predicates, input-order determinism, engine scan smoke + cross-scan stability.


### Phase 18 — Visualization

- `gui/viz/base.py` — `VizWidget` canvas: one `draw()` feeds the screen and in-memory PNG (`QImage`) / SVG (`QSvgGenerator`) exports; `export_png`/`export_svg` write report files (S18.5).
- `gui/viz/graph_widget.py` — entity relationship graph built from the Phase 16 correlation payload; dependency-free deterministic Fruchterman-Reingold layout (no numpy needed), edges colored by type, target ring highlight (S18.1).
- `gui/viz/timeline.py` — scan + news timeline on a shared time axis with `timeline_events()` normalizing payloads (S18.2).
- `gui/viz/charts.py` — paint-based risk-category pie, module/severity bar charts, and scan trend line with `severity_bars`/`module_bars`/`trend_points` helpers (S18.3).
- `gui/viz/world_map.py` — offline tile-less coarse world map (committed 135-country polygon set) dotting `Geo: IP location` findings by country or explicit lat/lon (S18.4).
- `gui/pages/results.py` — new Visualization tab (Graph/Timeline/Charts/Map); `normalize_result` now passes `correlation`/`risk` through.
- 8 new tests: offscreen widget PNG/SVG rendering, deterministic graph export, timeline sorting/dedup, bar helpers, map grouping, PNG file writes, results-page wiring.

# Changelog

All notable changes to IntelXtract are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


### Phase 15 — News Module

- `modules/news/` — Google News RSS + configured RSS/Atom feeds (`rss.py`, `feeds.py`, `timeline.py`, `collector.py`).
- Deterministic timeline builder: dedupe by URL/guid, newest-first, undated last, capped by `news.max_items`.
- Config: `news.{google,max_items,feeds,feeds_by_domain,feeds_extra}`; registered `modules.news` on DOMAIN deep scans.
- Offline-safe: every feed failure degrades to an `unavailable` LOW finding rather than crashing.
- 21 new tests (feed fixtures, date parsing, dedupe, feeds config, engine + persistence).

## [Unreleased]

### Added

- Phase 9 — IP module: three collectors under `modules/ip/`. `geo.py`
  resolves coarse location plus ISP/ASN/organization from the keyless
  ip-api.org endpoint and caches successful lookups in the engine cache for
  ``geo.cache_ttl`` (default 24h). `rdns.py` performs reverse DNS over
  DNS-over-HTTPS for both IPv4 (`in-addr.arpa`) and IPv6 (`ip6.arpa`) and
  re-resolves each PTR hostname for a forward-confirmed (FCrDNS) match.
  `reputation.py` probes the Spamhaus ZEN DNSBL (delisting codes
  127.0.0.2-11 classified as SBL/XBL/CSS/PBL) over DoH and, only when an
  ``abuseipdb`` API key is configured, checks AbuseIPDB report score. IPv6
  targets are reported as out-of-scope for the IPv4-only DNSBL. Every data
  source degrades to a LOW finding / ``degraded`` state instead of failing
  the scan; the quick/deep IP selection maps now list the three modules and
  the CLI/engine register them. Tests cover cached geo lookups (cache-hit
  path), forward-confirmed and mismatched reverse records, clean/listed/
  IPv6 DNSBL, keyed and keyless AbuseIPDB, offline degradation, and IPv4 +
  IPv6 deep scans persisted end-to-end into SQLite.
- Phase 10 — website module: five collectors under `modules/website/`.
  `headers.py` profiles the final response (server/X-Powered-By disclosure →
  MEDIUM, compression, six security headers present/missing, cookie flags
  Secure/HttpOnly/SameSite with insecure cookie findings by severity).
  `tech_stack.py` fingerprints CMS/frameworks/libs from headers, cookies, and
  HTML against an internal signature table (WordPress, Drupal, Joomla,
  nginx, Apache, Cloudflare, Django, Laravel, React, Vue, jQuery, Bootstrap,
  Webpack, Gatsby). `favicon.py` fingerprints `/favicon.ico` as
  FNV-1a(base64(md5(icon))) for external cross-site correlation. `robots.py`
  parses robots.txt into user-agent groups (allow/disallow/crawl-delay,
  max disallow depth) and extracts sitemap URLs from robots-declared and
  `/sitemap.xml`. `http_methods.py` probes OPTIONS/HEAD/GET for allowed
  methods (TRACE → MEDIUM), page title, and content type; a new
  `HttpClient.request(method, …)`/`BaseModule.http_fetch` supports the
  non-GET probes with the same non-raising retry semantics. URL quick depth
  now selects headers + http_methods and the deep profile selects all five
  website collectors (plus domain/certificate); CLI/engine register them.
  Tests use an HTML fixture corpus (`tech.html`, `robots.txt`, `sitemap.xml`,
  favicon bytes) covering detection, cookie parsing, missing-protection and
  TRACE severities, and IPv4/IPv6-styled deep scans persisted to SQLite.
- Phase 11 — email module: address classification via `modules/email/`.
  `validation.py` syntax-checks, splits local/domain, and flags disposable
  providers against a bundled blocklist (extendable via
  `email.disposable_extra`). `mx.py` probes mail infrastructure over the
  shared DoH endpoint: MX presence with host A-resolution, SPF
  (includes + all-qualifier) and DMARC (policy/pct) parsing. `gravatar.py`
  probes the public avatar endpoint with `d=404` for existence. The two
  registered collectors are `EmailModule` ("email", validation + MX/SPF/DMARC
  + Gravatar with per-stage degradation to low-severity findings) and
  `BreachModule` ("breach", HIBP v3, `requires_keys=("hibp",)`). A missing
  API key emits a planner-level "skipped" run instead of an error, per the
  done criteria; unauthorized keys surface a MEDIUM finding. New
  `HttpClient.request`/`fetch`/`BaseModule.http_fetch` accept extra `headers`
  (for the HIBP API key). EMAIL deep profile selects
  email + breach + domain; quick selects the email collector. Tests cover
  syntax/blocklist units, mocked DoH+avatar+HIBP probes (200/404/401/503/
  transport), and quick/deep engine scans persisted to SQLite.
- Phase 12 — username module: presence checks across 36 bundled public
  profile sites (`modules/username/sites.json` with per-site status/marker
  rules; operator sites via `username.sites_extra` or a full
  `username.sites_path` override). `social.py` probes sites concurrently with
  a global semaphore plus per-site request pacing, resolving each verdict
  conservatively: only conclusive status codes or body markers yield
  exists/missing, anything else (redirects, bot walls, 5xx) is `unknown`.
  `enrichment.py` parse-lightly pulls the public GitHub profile (avatar,
  display name, bio, stats) when the account exists; blocks/rate limits
  quietly skip it. The registered `username` collector emits an INFO finding
  per confirmed profile plus a `Username: profile summary` aggregate, and
  marks the run `degraded` (LOW finding) when every verdict is unknown.
  Tests cover registry validation, exists/missing/blocked/odd-status verdicts,
  marker precedence (Instagram-style 200 + missing-marker), enrichment
  failure modes, and mocked quick scans persisted to SQLite.
- Phase 13 — certificate module: deep TLS/certificate intelligence in three
  parts. `details.py` parses captured PEM/DER certificates (cryptography)
  into subject/issuer DNs, SANs, signature algorithm, serial, validity,
  key/extended-key usage, CA flag, CT poison mark and SCT list, with
  pure-data risk classification (weak SHA-1/MD5 signatures, expired or
  expiring-soon certs, self-signed, precertificates). `tls_probe.py`
  handshakes TLS 1.0–1.3 per version and reports the negotiated cipher,
  flagging deprecated protocols and RC4/3DES/CBC/NULL/EXPORT ciphers.
  `transparency.py` aggregates crt.sh history — issuers, validity windows,
  SAN sets, first/last seen, wildcard-normalized related names. The
  registered `certificate` collector combines all three, degrading to
  `partial`/`unknown` when the live handshake or crt.sh is unavailable.
  Live hooks are module-level and monkeypatched in tests, so no unit test
  opens a TLS connection; certificate fixtures are built offline.
- Phase 14 — metadata module: document/file property extraction for
  user-provided files. `pdf.py` reads PDF document dictionaries via pypdf
  (title, author, producer, creator, page count, PDF version, creation/mod
  timestamps normalized to ISO-8601). `image.py` reads only EXIF header
  blocks with Pillow — make/model, software, timestamps, artist, lens — and
  converts GPS DMS rationals to signed decimal degrees, guarded by a
  decompression-bomb pixel cap and never decoding pixel payloads. `office.py`
  parses OOXML ``.docx``/``.xlsx``/``.pptx`` core/app property parts
  directly from the zip container (creator, lastModifiedBy, company, dates,
  application), with legacy binary ``.doc`` explicitly out of scope. The
  registered `metadata` collector dispatches on extension and collapses
  malformed or unsupported files to informational findings instead of
  failing the scan. Fixture files (sample PDF/JPEG/docx + malformed
  variants) are committed under `tests/modules/fixtures/metadata/`.
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
- Phase 7 — module system: `core/models.py` with the `Finding` dataclass
  (`module`, `title`, `severity`, `confidence`, `data`, `evidence`,
  `collected_at`) normalized from raw module output, deduplicated by a stable
  SHA-256 content hash, and carried on `ModuleResult`; `modules/base.py`
  `BaseModule` ABC (metadata, `validate`, `run`, `parse`, `export`, timeout/
  retry hooks) and `modules/registry.py` `ModuleRegistry` for discovery of
  packages under `modules/`, name-collision handling, and per-name enable/
  disable; `core/http_client.py` lazily-constructed aiohttp `HttpClient` with
  retry; the engine's `ModuleContext` now carries the shared HTTP session and
  an `api_key()` accessor, plans skip modules with unconfigured
  `requires_keys`, extracts and dedupes `ModuleResult` findings, and closes
  the HTTP client per scan; DB migration 2 adds `findings.title`, `evidence`,
  `content_hash`, and `collected_at` persisted through `FindingRepository`;
  reusable test harness under `tests/modules/` (`DummyModule`,
  `KeyedDummyModule`, `FakeHttpClient`, `make_module_context`) with the dummy
  module executing end-to-end through the engine into SQLite.
- `.env` support in `core/config.py` (`load_env_file`): API keys and other
  secrets can live in a git-ignored `.env` file (template in
  `.env.example`); existing environment variables are never overridden.
- Phase 8 — domain module: five collectors under `modules/domain/` —
  `whois.py` (RDAP registrar/dates/nameservers/contacts with email-redaction
  option and DNSSEC status), `dns.py` (DoH A/AAAA/CNAME/NS/MX/TXT plus SPF,
  DMARC, and a bounded DKIM selector probe), `ssl.py` (stdlib asyncio TLS
  handshake exposing subject, issuer, validity, SANs, and self-signed/
  expired flags), `subdomain.py` (passive certificate-transparency listing
  via crt.sh), and `http.py` (https/http probes, redirect chains,
  robots.txt/sitemap.xml reachability, and pass-fail security-header checks
  for HSTS/CSP/XFO/referrer/permissions). `HttpClient.fetch()` returns a
  non-raising `HttpResponse` (status/headers/body/redirects) for the probes;
  the quick/deep selection maps now list the domain modules; the CLI scan
  registers the discovered domain collectors. All network access is mocked
  in tests via `tests/modules/fixtures/` recorded payloads (RDAP/DoH/crt.sh/
  HTTP), covering each module plus an end-to-end engine run persisted into
  SQLite.

### Fixed

- Removed the hard-coded placeholder API key from the Phase 7 test harness
  (`tests/modules/fakes.py`); secrets are no longer committed and instead
  flow from the environment or the `.env` file.

[Unreleased]: https://keepachangelog.com/en/1.1.0/
