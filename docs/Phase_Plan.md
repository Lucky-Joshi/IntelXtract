# IntelXtract Phase Plan

Living execution plan for the IntelXtract roadmap. Each phase is broken into
sub-phases that are small enough to implement and verify independently.

## How this plan works

1. **One phase per session.** Implementation stops when a phase is complete.
2. **Report protocol.** When a phase finishes, work stops and a summary is
   reported (sub-phases done, files added, verification results). The next
   phase starts only after an explicit "continue".
3. **Scope changes happen between phases**, never mid-phase. New scope is
   added to this document first, then implemented.
4. **Verification is mandatory.** Before a phase is marked `done`:

   ```bash
   ruff check . && black --check . && mypy . && pytest
   ```

   (Minimal gate for early phases; each phase may add its own checks.)

## Status legend

| Status        | Meaning                              |
|---------------|--------------------------------------|
| `[ ]`         | Pending                              |
| `[~]`         | In progress                          |
| `[x]`         | Done — verified and reported         |
| `[-]`         | Deferred / skipped (reason noted)    |

## Milestones

| Milestone | Name                  | Phases   |
|-----------|-----------------------|----------|
| A         | Planning & Foundation | 0–1      |
| B         | Core Engine           | 2–4      |
| C         | Interface             | 5        |
| D         | Collection Modules    | 6–15     |
| E         | Intelligence          | 16–17    |
| F         | Presentation          | 18–19    |
| G         | Platform & Extensibility | 20–21 |
| H         | Collaboration & AI    | 22–23    |
| I         | Hardening & Release   | 24–29    |

---

## Phase summary

| Phase | Name                       | Milestone | Size | Status |
|-------|----------------------------|-----------|------|--------|
| 0     | Planning                   | A         | S    | [x]    |
| 1     | Project Foundation         | A         | M    | [x]    |
| 2     | Core Architecture          | B         | L    | [ ]    |
| 3     | Database                   | B         | M    | [ ]    |
| 4     | CLI                        | B         | M    | [ ]    |
| 5     | GUI                        | C         | XL   | [ ]    |
| 6     | Input Engine               | D         | S    | [ ]    |
| 7     | Module System              | D         | M    | [ ]    |
| 8     | Domain Module              | D         | L    | [ ]    |
| 9     | IP Module                  | D         | M    | [ ]    |
| 10    | Website Module             | D         | M    | [ ]    |
| 11    | Email Module               | D         | M    | [ ]    |
| 12    | Username Module            | D         | M    | [ ]    |
| 13    | Certificate Module         | D         | M    | [ ]    |
| 14    | Metadata Module            | D         | M    | [ ]    |
| 15    | News Module                | D         | S    | [ ]    |
| 16    | Correlation Engine         | E         | L    | [ ]    |
| 17    | Risk Engine                | E         | M    | [ ]    |
| 18    | Visualization              | F         | L    | [ ]    |
| 19    | Reporting                  | F         | L    | [ ]    |
| 20    | Plugin SDK                 | G         | M    | [ ]    |
| 21    | Scheduler                  | G         | M    | [ ]    |
| 22    | Case Management            | H         | M    | [ ]    |
| 23    | AI Assistant (optional)    | H         | S    | [ ]    |
| 24    | Settings                   | I         | M    | [ ]    |
| 25    | Performance                | I         | M    | [ ]    |
| 26    | Testing                    | I         | L    | [ ]    |
| 27    | Documentation              | I         | M    | [ ]    |
| 28    | Packaging                  | I         | M    | [ ]    |
| 29    | Version 1.0 Release        | I         | M    | [ ]    |

Size: S < 1 day · M 1–3 days · L 3–7 days · XL > 7 days.

---

## Phase 0 — Planning

**Objective:** Brand identity, folder architecture, and governance documents.
No application code.

- [x] S0.1 Brand identity — `assets/logo.svg`, `assets/icon.svg` (vector
      monogram, shield + magnifier motif)
- [x] S0.2 Color palette & typography — `docs/brand/BRAND.md` (hex palette,
      UI font stack, spacing/radius tokens, logo usage rules)
- [x] S0.3 Folder architecture — top-level skeleton from the roadmap with
      `.gitkeep` placeholders
- [x] S0.4 Coding standards — `docs/coding_standards.md` (naming, typing,
      async rules, error handling, docstring policy)
- [x] S0.5 Development workflow — `docs/git_workflow.md` (branch naming,
      commit style, phase gate process)
- [x] S0.6 Threat model — `docs/threat_model.md` (assets, adversaries,
      API-key handling, scope/ethics boundaries)
- [x] S0.7 Privacy statement — `docs/privacy.md` (local-first storage, what
      is collected, what is never collected)

**Deliverables:** `assets/*.svg`, `docs/brand/BRAND.md`, `docs/coding_standards.md`,
`docs/git_workflow.md`, `docs/threat_model.md`, `docs/privacy.md`, folder skeleton.

**Done criteria:** All files exist; brand tokens are concrete (hex values,
font names); folder skeleton matches the roadmap structure.

**Depends on:** —

---

## Phase 1 — Project Foundation

**Objective:** Repository files, uv environment, tooling, CI, initial commit.

- [x] S1.1 Repo documents — `README.md`, `LICENSE` (GPL v3 full text),
      `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant),
      `CHANGELOG.md` (Keep a Changelog), `SECURITY.md`, `ROADMAP.md`
- [x] S1.2 `.gitignore` — Python, venv, `logs/`, `cache/`, `exports/`,
      `__pycache__`, IDE/OS noise
- [x] S1.3 Environment — `uv venv .venv`; `requirements.txt` (runtime:
      `aiohttp`, `typer`, `rich`, `jinja2`); `requirements-dev.txt`
      (`ruff`, `black`, `mypy`, `pytest`, `pytest-asyncio`); install both
- [x] S1.4 Tool config — `pyproject.toml` with `[tool.ruff]`, `[tool.black]`,
      `[tool.mypy]`, `[tool.pytest.ini_options]` only (no `[project]` table)
- [x] S1.5 Folder skeleton — `app/ core/ modules/ plugins/ database/ gui/ cli/
      reports/ templates/ exports/ assets/ config/ tests/ scripts/ examples/`
- [x] S1.6 CI — `.github/workflows/ci.yml` (ruff, black, mypy, pytest on
      Python 3.13/3.14; dormant until a remote exists)
- [x] S1.7 Smoke test — `tests/test_sanity.py`; full gate green:
      `ruff check . && black --check . && mypy . && pytest`
- [x] S1.8 Git init + single initial commit (no remote, no push)

**Deliverables:** repo docs, toolchain, venv, CI config, first commit.

**Done criteria:** Verification gate passes inside the venv; `git log` shows
the initial commit.

**Depends on:** Phase 0

---

## Phase 2 — Core Architecture

**Objective:** Framework only — engine, config, logging, cache, scheduler,
worker pool, plugin loader. No OSINT modules, no GUI.

- [ ] S2.1 `core/constants.py` + `core/exceptions.py` — target types, severities,
      custom exception hierarchy
- [ ] S2.2 `core/config.py` — layered settings (defaults → `config/settings.json`
      → env vars), load/save/get with dotted keys
- [ ] S2.3 `core/logger.py` — console + rotating file logging in `logs/`,
      levels from config, scan-id context binding
- [ ] S2.4 `core/cache.py` — async TTL cache with size cap and per-key expiry
- [ ] S2.5 `database/connection.py` — async SQLite connection factory
      (`aiosqlite`), open/close helpers (schema arrives in Phase 3)
- [ ] S2.6 `core/plugin_loader.py` — `PluginBase` protocol + directory
      discovery + enable/disable registry
- [ ] S2.7 `core/scheduler.py` — FIFO task queue with priorities and status
      tracking (queued/running/done/failed)
- [ ] S2.8 `core/worker_pool.py` — asyncio worker pool: concurrency limit,
      cancellation, per-task timeout, result collection
- [ ] S2.9 `core/engine.py` — orchestrator facade wiring input → plan → queue
      → pool → results (pipeline runs with zero modules registered)
- [ ] S2.10 Unit tests for each component (mock I/O, no network)

**Deliverables:** `core/*`, `database/connection.py`, tests.

**Done criteria:** `pytest` green; a programmatic engine run completes an
empty scan pipeline and returns a structured result object.

**Depends on:** Phase 1

---

## Phase 3 — Database

**Objective:** Schema, migrations, and repository layer.

- [ ] S3.1 Schema design doc — expand `docs/Database_Schema.md` with columns,
      types, indexes, foreign keys, relationships (ER diagram in text)
- [ ] S3.2 `database/schema.sql` — tables: `targets`, `scans`, `findings`,
      `reports`, `plugins`, `api_keys`, `logs`, `history`, `settings`
- [ ] S3.3 `database/migrations.py` — versioned migration runner
      (`schema_version` table, forward migrations only for now)
- [ ] S3.4 `database/repositories.py` — typed CRUD for targets/scans/findings/
      reports/settings (used by engine, CLI, GUI)
- [ ] S3.5 Tests — create/migrate/query round-trip on a temp database

**Deliverables:** schema, migration runner, repositories, tests.

**Done criteria:** Fresh DB migrates to latest version; repositories pass
round-trip tests; no table access outside the repository layer.

**Depends on:** Phase 2

---

## Phase 4 — CLI

**Objective:** Typer-based command-line interface.

- [ ] S4.1 CLI skeleton — `cli/main.py`, app group, `--version`, `--verbose`,
      entry point aliasable as `intelxtract`
- [ ] S4.2 `scan` — target argument, `--mode quick|deep|custom`,
      `--modules` filter, `--format`, live rich progress from worker pool
- [ ] S4.3 `report` — regenerate/export reports for a past scan id
      (`html|pdf|json|csv|md`; formats land in Phase 19, stubs return JSON)
- [ ] S4.4 `history` — list scans, show scan detail, filter by target/status
- [ ] S4.5 `config` — `get` / `set` / `list` / `path` on dotted config keys
- [ ] S4.6 `plugin` — `list` / `enable` / `disable` / `info`
- [ ] S4.7 `doctor` — Python version, venv detection, DB writable, config
      valid, network reachability probe, dependency versions
- [ ] S4.8 `update` — compare installed version against PyPI (informational)
- [ ] S4.9 Tests — `typer.testing.CliRunner` coverage for every command

**Deliverables:** `cli/` package, console entry point, CLI tests.

**Done criteria:** All seven commands run and exit 0 with useful output;
CLI tests green.

**Depends on:** Phases 2–3 (uses Phase 6+ modules as they arrive)

---

## Phase 5 — GUI

**Objective:** PySide6 desktop application shell with all pages stubbed and
wired to the core engine.

- [ ] S5.1 App shell — main window, sidebar navigation, dark theme QSS built
      from BRAND.md tokens, status bar
- [ ] S5.2 Dashboard — scan queue, recent scans, active tasks, threat summary,
      stats widgets, plugin status, API usage, log tail (live from engine)
- [ ] S5.3 Quick Scan — single target, fast module set, one-click run
- [ ] S5.4 Deep Scan — full module set with module checklist (custom mode)
- [ ] S5.5 Results — tabbed findings view per module + correlation panel stub
- [ ] S5.6 Reports — list generated reports, export shortcuts
- [ ] S5.7 History — past scans table with filters and diff entry point
- [ ] S5.8 Plugins — discovered plugins, enable/disable, manifest details
- [ ] S5.9 API Manager — API keys per provider (writes to vault from Phase 24;
      interim: config storage with warning banner)
- [ ] S5.10 Settings — theme, paths, rate limits, timeouts, cache, DB, logging
- [ ] S5.11 About — version, license, links
- [ ] S5.12 Engine bridge — background `QThread`/worker running asyncio engine,
      signals for progress/results into Qt main thread
- [ ] S5.13 Smoke test — launch offscreen (`QT_QPA_PLATFORM=offscreen`),
      navigate every page, assert no crashes

**Deliverables:** `gui/` package, QSS theme, offscreen smoke tests.

**Done criteria:** App launches, every page opens, a scan can be started from
GUI and results appear; offscreen tests green.

**Depends on:** Phases 2–4 (pages fill in as later phases land; stubs allowed)

---

## Phase 6 — Input Engine

**Objective:** Automatic target detection, validation, and module selection.

- [ ] S6.1 Target classifier — regex rules for domain, IP (v4/v6), URL,
      email, username, hash (md5/sha1/sha256), file path; precedence order
      documented
- [ ] S6.2 Validator & normalizer — syntax checks, lowercase/punycode for
      domains, URL scheme defaulting, trim/whitespace handling, clear
      rejection errors
- [ ] S6.3 Module selection map — target type → eligible module names,
      consumed by scan planner (quick/deep/custom profiles)
- [ ] S6.4 Tests — table-driven classification/validation cases including
      edge cases (IDN, IPv6, ports, `user@host`, bare usernames)

**Deliverables:** `core/input_engine.py` (or `core/target.py`), selection map,
tests.

**Done criteria:** Every supported input type classifies correctly; invalid
inputs produce actionable errors; tests green.

**Depends on:** Phase 2

---

## Phase 7 — Module System

**Objective:** Uniform interface every collector implements.

- [ ] S7.1 `BaseModule` ABC — `name`, `target_types`, `requires_keys`,
      `validate(target)`, `async run(target, ctx) -> ModuleResult`,
      `parse(raw)`, `export(result)`; shared timeout/retry hooks
- [ ] S7.2 Registry — module discovery (import packages under `modules/`),
      collision handling, enable/disable per profile
- [ ] S7.3 Normalizer — `Finding` dataclass (`module`, `title`, `severity`,
      `confidence`, `data`, `evidence`, `collected_at`) + dedupe by content hash
- [ ] S7.4 Context object — config, cache, logger, HTTP session, API-key
      accessor handed to every `run()`
- [ ] S7.5 Test harness — shared pytest fixtures (mock HTTP, fake context)
      + one dummy module proving the contract end-to-end

**Deliverables:** `modules/base.py`, `modules/registry.py`, `core/models.py`,
test harness.

**Done criteria:** Dummy module executes through the engine and its findings
normalize and persist; harness reusable by Phase 8 tests.

**Depends on:** Phases 2–3, 6

---

## Phase 8 — Domain Module

**Objective:** Full domain intelligence collection.

- [ ] S8.1 `modules/domain/whois.py` — registrar, dates, nameservers,
      contacts (email redaction option), DNSSEC status
- [ ] S8.2 `modules/domain/dns.py` — A/AAAA/CNAME/NS/MX/TXT, SPF, DKIM
      selector probe, DMARC, record raw values
- [ ] S8.3 `modules/domain/ssl.py` (basic) — certificate subject, issuer,
      validity, SAN list, self-signed/expired flags (deep chain work → Phase 13)
- [ ] S8.4 `modules/domain/subdomain.py` — passive sources only
      (certificate transparency via crt.sh, public datasets)
- [ ] S8.5 `modules/domain/http.py` — HTTP/HTTPS status, redirect chain,
      robots.txt/sitemap.xml reachability, security-header *checks*
      (HSTS/CSP/XFO/referrer/permissions → pass-fail findings for risk engine)
- [ ] S8.6 Tests — all network mocked; record fixtures for WHOIS/DNS/HTTP

**Boundary note:** Phase 10 owns raw website profiling (title, cookies, tech).
Phase 8 owns record/infrastructure facts and pass-fail security checks.

**Done criteria:** `intelxtract scan example.com --mode deep` (once CLI +
modules land) produces WHOIS/DNS/SSL/subdomain/HTTP findings; tests green.

**Depends on:** Phase 7

---

## Phase 9 — IP Module

**Objective:** IP address intelligence.

- [ ] S9.1 `modules/ip/geo.py` — ASN, ISP, country/region/city (coarse),
      organization; free API with cache + graceful degradation offline
- [ ] S9.2 `modules/ip/rdns.py` — reverse DNS (v4/v6), forward-confirmed
      lookup
- [ ] S9.3 `modules/ip/reputation.py` — authorized/conservative sources only
      (e.g., Spamhaus ZEN DNSBL, optional AbuseIPDB when key present)
- [ ] S9.4 Tests — mocked API/DNSBL responses, cache-hit paths

**Done criteria:** IPv4 and IPv6 targets scan end-to-end; no scan fails hard
when a source is unavailable (partial results + degraded status).

**Depends on:** Phase 7

---

## Phase 10 — Website Module

**Objective:** Deep website profiling beyond Phase 8's checks.

- [ ] S10.1 `modules/website/headers.py` — full response headers, server/
      powered-by disclosure, compression (gzip/brotli), cookies
      (flags: Secure/HttpOnly/SameSite)
- [ ] S10.2 `modules/website/tech_stack.py` — CMS/framework/library detection
      from headers + HTML/JS signature rules (internal rule table, no
      third-party fingerprint API)
- [ ] S10.3 `modules/website/favicon.py` — favicon fetch + hash
      (mmh3-style fingerprint for external correlation)
- [ ] S10.4 `modules/website/robots.py` — robots.txt parse (groups,
      disallow depth), sitemap.xml URL extraction (shared with Phase 8 fetch)
- [ ] S10.5 `modules/website/http_methods.py` — OPTIONS/HEAD probe for
      allowed methods, page title, content type
- [ ] S10.6 Tests — HTML fixture corpus for the detection rules

**Done criteria:** Tech detection matches fixtures; insecure cookie/method
findings emitted with severity; tests green.

**Depends on:** Phases 7–8

---

## Phase 11 — Email Module

**Objective:** Email address intelligence within API terms.

- [ ] S11.1 `modules/email/validation.py` — syntax, domain existence,
      disposable-domain blocklist (bundled list, updatable)
- [ ] S11.2 `modules/email/mx.py` — MX presence, SPF/DMARC on the domain,
      MX host resolution
- [ ] S11.3 `modules/email/gravatar.py` — Gravatar existence via MD5 hash
      probe (public endpoint)
- [ ] S11.4 `modules/email/breach.py` — breach checks only where the provider
      permits API use (key-gated, e.g., HIBP); graceful skip when no key
- [ ] S11.5 Tests — syntax/blocklist unit tests, mocked network probes

**Done criteria:** Valid/invalid/disposable inputs classified correctly;
missing API keys produce "skipped" status, not errors.

**Depends on:** Phases 7, 24-lite (key access via config; vault hardening later)

---

## Phase 12 — Username Module

**Objective:** Public username presence checks.

- [ ] S12.1 Site pattern list — `modules/username/sites.json` (name, URL
      template, response rule: status code / body marker)
- [ ] S12.2 `modules/username/social.py` — async batch probe of profile URLs,
      existence verdict per site (conservative: unknown ≠ not-found)
- [ ] S12.3 Enrichment — where publicly exposed without auth: avatar URL,
      display name, bio, profile URL; parse-light (no scraping beyond public
      profile page, respects robots/rate limits)
- [ ] S12.4 Tests — mocked responses per verdict type (exists/missing/blocked)

**Done criteria:** 30+ sites probed concurrently with per-site rate limits;
verdicts tested; blocked sites reported as `unknown`.

**Depends on:** Phase 7

---

## Phase 13 — Certificate Module

**Objective:** Deep TLS/certificate intelligence (extends S8.3).

- [ ] S13.1 Chain & details — full chain fetch, issuer/subject DNs, SAN
      enumeration, signature algorithm, serial, CT poison/extension flags
- [ ] S13.2 TLS probe — supported protocol versions (TLS 1.0–1.3),
      negotiated cipher, weak-cipher/protocol findings
- [ ] S13.3 Certificate transparency — historical certs for domain via crt.sh
      (issuers, validity windows, SAN sets, first/last seen)
- [ ] S13.4 Tests — captured cert fixtures, no live TLS in unit tests

**Done criteria:** Cert findings feed correlation (SANs → related domains)
and risk (expiry, weak protocol); tests green.

**Depends on:** Phases 7–8

---

## Phase 14 — Metadata Module

**Objective:** Document/file metadata extraction (user-provided files).

- [ ] S14.1 `modules/metadata/pdf.py` — title, author, producer, creation/
      modification dates, PDF version (`pypdf`)
- [ ] S14.2 `modules/metadata/image.py` — EXIF: camera, software, timestamps,
      GPS if present (`Pillow`); safe parsing of untrusted files
- [ ] S14.3 `modules/metadata/office.py` — OOXML core/app properties
      (author, company, dates) via zip/XML parse; legacy `.doc` note as
      out-of-scope for v1
- [ ] S14.4 Tests — small fixture files under `tests/fixtures/`

**Done criteria:** All three parsers extract expected fields from fixtures;
malformed files fail gracefully.

**Depends on:** Phase 7

---

## Phase 15 — News Module

**Objective:** Recent news and press mentions for entity targets.

- [ ] S15.1 `modules/news/rss.py` — Google News RSS / public RSS search by
      domain-or-organization keyword (no key required)
- [ ] S15.2 `modules/news/feeds.py` — configurable RSS/Atom feed list per
      case/domain, dedupe by URL/guid
- [ ] S15.3 Timeline builder — normalized article records (title, source,
      date, url) ordered newest-first for report timeline
- [ ] S15.4 Tests — feed fixtures, date parsing, dedupe logic

**Done criteria:** A domain scan yields a news timeline; offline/failed feed
fetches degrade gracefully.

**Depends on:** Phase 7

---

## Phase 16 — Correlation Engine

**Objective:** Link findings into entities and relationships — the platform's
core differentiator.

- [ ] S16.1 Entity model — `core/entities.py`: domain, subdomain, email,
      username, IP, organization, certificate, phone, document, social
      profile, technology; stable entity IDs (type + normalized value hash)
- [ ] S16.2 Extractors — per-module entity extraction from `Finding.data`
      (registry pattern so modules declare their entities)
- [ ] S16.3 Linker — relationship edges with type + confidence
      (`resolves_to`, `registered_by`, `issued_to`, `same_email`, `mentions`…)
- [ ] S16.4 Graph output — NetworkX graph → JSON (nodes/edges) for viz +
      persistence in `findings`/`history`
- [ ] S16.5 Tests — fixture scan → expected entity set + edge set;
      determinism check (same input → same graph)

**Done criteria:** A domain scan produces a connected graph linking domain →
cert → IPs → emails; graph JSON stable and tested.

**Depends on:** Phases 7–15 (works incrementally as modules land)

---

## Phase 17 — Risk Engine

**Objective:** Weighted, explainable risk scoring.

- [ ] S17.1 Rule set — `core/risk_rules.py`: finding pattern → weight
      (expired SSL, missing HSTS/CSP, weak SPF, no DMARC, exposed emails,
      breach hits, open methods, insecure cookies, …)
- [ ] S17.2 Scorer — 0–100 score → `low | medium | high | critical`, per-
      category sub-scores (TLS, headers, DNS hygiene, exposure)
- [ ] S17.3 Summary generator — top risks in plain language (feeds reports
      and AI assistant prompts)
- [ ] S17.4 Tests — golden tests: fixture finding sets → expected scores

**Done criteria:** Scores deterministic and documented; every contributing
rule traceable in output.

**Depends on:** Phase 16 (consumes normalized findings; runs even without it)

---

## Phase 18 — Visualization

**Objective:** Graphs, timelines, and charts in GUI and reports.

- [ ] S18.1 Relationship graph widget — interactive node graph in GUI
      (QGraphicsScene-based or pyqtgraph; layout via NetworkX)
- [ ] S18.2 Timeline view — scans + news + cert validity on a time axis
- [ ] S18.3 Charts — risk distribution pie, module/severity bars, scan
      statistics trend (pyqtgraph or exported Plotly images for reports)
- [ ] S18.4 World map — coarse IP geolocation map (static image or simple
      tile-less plot; no external tile service required)
- [ ] S18.5 Export helpers — render each viz to PNG/SVG for report embedding
- [ ] S18.6 Smoke tests — widget construction offscreen, chart render to bytes

**Done criteria:** GUI shows live graph/timeline/charts for a sample scan;
PNG exports embeddable.

**Depends on:** Phases 5, 16–17

---

## Phase 19 — Reporting

**Objective:** Multi-format reports with shared content model.

- [ ] S19.1 Report model — `reports/builder.py`: assemble executive summary,
      findings, risk overview, timeline, evidence refs, methodology,
      timestamp from scan + correlation + risk data
- [ ] S19.2 HTML — Jinja2 templates in `templates/` styled from BRAND.md
- [ ] S19.3 JSON / CSV / Markdown exporters
- [ ] S19.4 PDF — WeasyPrint rendering of the HTML template; if system
      libraries are missing, print-friendly HTML fallback + clear warning
- [ ] S19.5 `history` integration — reports registered in `reports` table,
      discoverable via CLI/GUI
- [ ] S19.6 Tests — golden HTML/JSON snapshots, CSV row counts, PDF fallback

**Done criteria:** One command produces all five formats for a sample scan;
files land in `exports/` and in the DB.

**Depends on:** Phases 16–17 (earlier phases may ship JSON-only stubs)

---

## Phase 20 — Plugin SDK

**Objective:** Stable third-party extension API.

- [ ] S20.1 Manifest schema — `manifest.json` (name, version, api_version,
      author, target types, required keys, entry point) + JSON-schema check
- [ ] S20.2 Loader hardening — version compatibility gate, isolated import
      errors (one bad plugin never breaks the app), enable/disable persisted
      in DB
- [ ] S20.3 Example plugins — `plugins/Wayback/` (CDX history) and
      `plugins/VirusTotal/` (key-gated domain report) as living references
- [ ] S20.4 SDK docs — `docs/plugin_sdk.md` + cookiecutter-style template
      under `plugins/_template/`
- [ ] S20.5 Tests — load/enable/disable/fail-soft paths, manifest validation

**Done criteria:** Example plugins run through the same pipeline as core
modules; broken plugin is reported, not fatal.

**Depends on:** Phases 7, 20 builds on Phase 2's loader

---

## Phase 21 — Scheduler

**Objective:** Recurring scans, change detection, resume.

- [ ] S21.1 Schedule model — `schedules` table (target, mode, cron/interval,
      enabled, last/next run) + repository
- [ ] S21.2 Runner — async scheduler loop, overlap prevention, persisted
      queue so interrupted scans resume
- [ ] S21.3 Change detection — diff findings between consecutive scans of
      the same target (added/removed/changed) → `history` entries
- [ ] S21.4 Hooks — CLI `schedule` commands + GUI surface (minimal table view)
- [ ] S21.5 Tests — fake clock, interval triggering, diff correctness

**Done criteria:** A daily schedule runs while app is open; diffs appear in
history; resume after kill mid-scan works.

**Depends on:** Phases 3–4 (GUI surface can follow Phase 5)

---

## Phase 22 — Case Management

**Objective:** Investigations grouping scans, notes, and evidence.

- [ ] S22.1 Schema — `cases`, `case_notes`, `case_evidence` tables +
      migration; link scans/findings to a case
- [ ] S22.2 Repository + CLI — `intelxtract case create|list|note|attach`
- [ ] S22.3 GUI — Cases page: create case, add notes, attach scans,
      view combined findings
- [ ] S22.4 Tests — repository round-trips, CLI coverage

**Done criteria:** A case can be created, populated with scans/notes, and
exported as a combined report.

**Depends on:** Phases 3–4, 19

---

## Phase 23 — AI Assistant (optional)

**Objective:** Grounded, optional assistance — never fabricates.

- [ ] S23.1 Provider abstraction — pluggable backends: disabled (default),
      any OpenAI-compatible endpoint (user-supplied URL + key); no data
      leaves the machine unless the user enables it (disclosed in UI)
- [ ] S23.2 Prompt templates — summarize report, explain a finding, compare
      two scans, suggest defensive next steps; prompts include raw evidence
      and an explicit "do not invent facts" constraint
- [ ] S23.3 Integration — CLI `intelxtract explain <scan>` + GUI assistant
      panel; every output labeled AI-generated and kept separate from findings
- [ ] S23.4 Tests — mocked provider, prompt assembly, refusal/empty paths

**Done criteria:** Feature is fully opt-in; disabled-by-default verified;
mocked tests green.

**Depends on:** Phases 17, 19

---

## Phase 24 — Settings

**Objective:** Centralized settings and secure key storage.

- [ ] S24.1 API key vault — encrypted at rest (Fernet key derived/stored with
      `keyring` when available, file-based fallback with strict 0600 perms),
      CLI/GUI set/get/delete; DB `api_keys` table stores ciphertext only
- [ ] S24.2 Network settings — proxy, rate limits, timeouts, retries
      (consumed by `core/context` HTTP layer)
- [ ] S24.3 App settings — theme, language, cache TTL/size, DB path,
      log level/rotation, telemetry = always off
- [ ] S24.4 GUI wiring — Settings page + API Manager write through the vault
      (replaces S5.9 interim storage)
- [ ] S24.5 Tests — vault round-trip, file perms, config precedence order

**Done criteria:** Keys never stored plaintext; all modules read keys via the
vault accessor; precedence documented and tested.

**Depends on:** Phases 2–4 (retrofits Phase 5 API Manager)

---

## Phase 25 — Performance

**Objective:** Make scans fast, polite, and resilient.

- [ ] S25.1 Connection pooling — shared `aiohttp.TCPConnector`, keep-alive,
      per-host limits
- [ ] S25.2 Cache integration — HTTP response caching (ETag/If-None-Match
      where supported), module-level result caching with TTL
- [ ] S25.3 Retry logic — exponential backoff + jitter, bounded attempts,
      retry only idempotent/transient failures
- [ ] S25.4 Offload blocking libs — WHOIS/DNS/metadata calls via
      `asyncio.to_thread` with a bounded thread pool
- [ ] S25.5 Concurrency policy — global + per-host semaphores, rate-limit
      tokens per API provider
- [ ] S25.6 Benchmarks — `scripts/bench.py` measuring scans/sec and cache
      hit rates; baseline numbers recorded in `docs/`

**Done criteria:** No blocking call on the event loop (verified by a slow-
task probe test); benchmarks reproducible; no unbounded concurrency.

**Depends on:** Phases 8–15

---

## Phase 26 — Testing

**Objective:** Systematic coverage across all layers.

- [ ] S26.1 Coverage tooling — `pytest-cov`, coverage config, CI report
- [ ] S26.2 Unit coverage push — target ≥ 80% on `core/`, `modules/`,
      `reports/`
- [ ] S26.3 Integration tests — end-to-end scan against a local mock HTTP
      server (no external network in CI)
- [ ] S26.4 CLI tests — full command matrix via `CliRunner`
- [ ] S26.5 GUI tests — pytest-qt offscreen: page navigation, scan start,
      result display
- [ ] S26.6 DB & plugin tests — migration from every released schema version;
      plugin load failure modes
- [ ] S26.7 Performance tests — budget assertions on cache/dedupe paths
- [ ] S26.8 CI gate — coverage threshold enforced in GitHub Actions

**Done criteria:** CI enforces lint + types + tests + coverage floor; suite
runs offline in < 2 minutes.

**Depends on:** Phases 4–5, 19 (grows with each phase; this phase closes gaps)

---

## Phase 27 — Documentation

**Objective:** Complete user and developer documentation.

- [ ] S27.1 Architecture docs — reconcile `docs/architecture.md`,
      `internal_architecture.md`, `Scan_Engine_Workflow.md` with the
      implemented system (single source of truth)
- [ ] S27.2 Installation & user guide — setup, CLI cookbook, GUI walkthrough,
      scan modes, report formats (`docs/user_guide.md`)
- [ ] S27.3 Developer guide — adding a module, running tests, code
      conventions link (`docs/developer_guide.md`)
- [ ] S27.4 Plugin SDK doc — finalize `docs/plugin_sdk.md` with full example
- [ ] S27.5 FAQ & troubleshooting — common errors, network/proxy issues,
      key setup (`docs/faq.md`, `docs/troubleshooting.md`)
- [ ] S27.6 README polish — screenshots, quickstart, badges, feature matrix

**Done criteria:** A new user can install, scan, and export a report using
only the docs; a developer can add a module without reading engine source.

**Depends on:** Phases 4–5, 19–20

---

## Phase 28 — Packaging

**Objective:** Distributable builds.

- [ ] S28.1 PyInstaller — spec files for Windows/Linux/macOS, asset bundling,
      smoke-run of frozen binary
- [ ] S28.2 Docker — multi-stage `Dockerfile` (headless/CLI image),
      `docker-compose.yml` with volume for DB/exports
- [ ] S28.3 PyPI — finalize `[project]` metadata in `pyproject.toml`,
      `intelxtract` console script, build/sdist check (optional publish)
- [ ] S28.4 Build scripts — `scripts/build_*.{sh,ps1}`, artifact checksums

**Done criteria:** Frozen binary runs a scan; Docker image builds and scans;
`python -m build` succeeds.

**Depends on:** Phases 4, 27

---

## Phase 29 — Version 1.0 Release

**Objective:** Ship a stable 1.0.

- [ ] S29.1 Release checklist — stable CLI + GUI, all core modules, reports,
      plugin examples, no critical open issues
- [ ] S29.2 CI/CD — release workflow: tag → build artifacts → draft GitHub
      release
- [ ] S29.3 Community files — issue templates (bug/feature/module request),
      PR template, `CODEOWNERS`
- [ ] S29.4 Example reports — sample outputs committed under `examples/`
      (sanitized targets)
- [ ] S29.5 Release notes — CHANGELOG 1.0.0 entry, migration notes, known
      limitations, ethical-use statement
- [ ] S29.6 Tag `v1.0.0` (tag only; pushing is user-owned)

**Done criteria:** Fresh install from release artifacts passes `doctor` and
completes a deep scan with HTML + PDF reports.

**Depends on:** Phases 26–28

---

## Unscheduled / future (post-1.0 backlog)

Items from the vision not yet assigned a phase:

- **REST API** (v4.0 roadmap) — HTTP service wrapping the engine
- **Watchlists & alerting** — monitored targets, change notifications
- **Threat intelligence feeds** — inbound feed ingestion
- **Batch scans** — hundreds of targets from file (partial CLI support may
  land early in Phase 4 as `--file`, promoted here when full-featured)
- **Team features** — shared workspaces, user accounts (v3.0 roadmap)
- **Localization** — language packs for the GUI

These are planned explicitly between phases, never mid-phase.

---

## Working rules

1. Phase status flips to `[x]` only after verification passes **and** the
   completion report is delivered.
2. Sub-phases within a phase are implemented in listed order unless a
   dependency forces otherwise (noted in the report).
3. Each phase ends with the standard gate:
   `ruff check . && black --check . && mypy . && pytest`
4. Git commits happen at phase boundaries (plus initial foundation commit);
   pushing requires explicit user instruction.
5. Roadmap order is preserved; deviations are recorded here first.
