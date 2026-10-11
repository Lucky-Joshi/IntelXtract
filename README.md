# IntelXtract

<p align="center">
  <img src="assets/logo.svg" alt="IntelXtract — OSINT Automation Platform" width="360">
</p>

**AI-powered OSINT automation & intelligence platform.**

IntelXtract collects, normalizes, correlates, analyzes, visualizes, and reports publicly available intelligence from many sources — WHOIS, DNS, SSL, HTTP, IP, email, usernames, certificate transparency, archives, news, and more — inside one unified interface instead of fifteen browser tabs.

> **Status: pre-alpha.** The project is being built phase-by-phase per the execution plan. See [`docs/Phase_Plan.md`](docs/Phase_Plan.md) for current progress and [`docs/Development_Plan.md`](docs/Development_Plan.md) for the full roadmap.

---

## Quickstart

```bash
# 1. Clone & enter
git clone https://github.com/yourorg/IntelXtract
cd IntelXtract

# 2. Create environment & install deps (Python 3.13+, uv required)
uv venv .venv
uv pip install -r requirements.txt -r requirements-dev.txt

# 3. Run a scan (CLI)
python -m cli.main scan example.com --mode deep

# 4. Launch the GUI
python -m gui.main

# 5. Verify everything works
ruff check . && black --check . && mypy . && pytest
```

---

## Badges

![Python](https://img.shields.io/badge/python-3.13+-blue)
![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green)
![Phase](https://img.shields.io/badge/phase-27--Documentation-blueviolet)
![Tests](https://img.shields.io/badge/tests-756%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-89.5%25-yellowgreen)

---

## Why IntelXtract

Most OSINT tools aggregate lookups. IntelXtract is built around four principles:

- **Automation** — one target in, a full multi-module scan out (quick, deep, custom, batch).
- **Correlation** — findings are linked into entities and relationship graphs, not left as isolated facts.
- **Visualization** — relationship graphs, timelines, maps, and risk charts.
- **Reporting** — polished HTML/PDF/JSON/CSV/Markdown reports with executive summary, evidence, and methodology.

---

## Feature Matrix

| Capability | Status | Modules / Details |
|------------|--------|-------------------|
| **Domain Intelligence** | ✅ | WHOIS/RDAP, DNS (A/AAAA/CNAME/MX/TXT/NS/SPF/DMARC/DKIM), SSL/TLS cert chain & SAN, Subdomain enumeration (crt.sh), HTTP headers & redirect chain, Tech stack fingerprinting, Favicon hash, robots.txt/sitemap, Certificate Transparency history, News/RSS timeline |
| **IP Intelligence** | ✅ | GeoIP (ASN, ISP, org, country, city, coords), Reverse DNS (PTR), Reputation (AbuseIPDB, GreyNoise — key-gated) |
| **Website / URL** | ✅ | Headers, HTTP methods (OPTIONS/TRACE), Tech stack, Favicon, robots.txt, Certificate extraction |
| **Email** | ✅ | Syntax validation, MX lookup, Disposable detection, Domain extraction, Breach lookup (HIBP — key-gated) |
| **Username** | ✅ | 100+ site presence checks via `sites.json`, Profile enrichment |
| **Certificate** | ✅ | Chain, TLS versions, CT log history, Serial, SAN, Related names |
| **File Metadata** | ✅ | PDF properties, Image EXIF, Office core properties |
| **Correlation Graph** | ✅ | NetworkX MultiDiGraph: entities (domain, IP, email, username, org, cert, doc, tech, social profile) + typed edges with confidence |
| **Risk Scoring** | ✅ | 30 deterministic rules across TLS (ceiling 40), Headers (30), DNS (20), Exposure (25); 0–100 score with critical/high/medium/low ratings |
| **Scheduled Scans** | ✅ | Interval or 5-field cron; overlap prevention; change detection (added/removed/changed findings) |
| **Case Management** | ✅ | Group scans/findings into investigations; combined reports |
| **Plugin SDK** | ✅ | Fail-soft discovery; `PluginBase` contract; key-gated modules; `PluginModuleAdapter` for engine parity |
| **CLI** | ✅ | `scan`, `report`, `history`, `config`, `plugin`, `schedule`, `case`, `key`, `doctor`, `serve` |
| **GUI** | ✅ | 13 pages: Dashboard, Quick/Deep Scan, Results (graph/timeline/risk), Reports, History, Cases, Schedules, Assistant, Plugins, API Manager, Settings, About |
| **Report Formats** | ✅ | JSON, CSV, Markdown, HTML (Jinja2 + brand tokens), PDF (WeasyPrint fallback) |
| **Encrypted Vault** | ✅ | `api_keys.*` stored encrypted in SQLite; `ctx.api_key()` accessor |
| **Performance** | ✅ | Pooled HTTP connector, exponential backoff+jitter, per-host semaphores/pacing, ETag/304 caching, thread offload pool, async TTL cache |

---

## Architecture

```text
CLI / GUI (PySide6)
        │
  Core Scan Engine ── Input Engine · Scheduler · Worker Pool
        │
  OSINT Modules (async, independent) + Plugin Modules
        │
  Correlation Engine → Risk Engine
        │
  SQLite (migrations v1→v4) + Repositories
        │
  HTML · PDF · JSON · CSV · Markdown Reports
```

Details: [`docs/architecture.md`](docs/architecture.md)

---

## Development Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv .venv
uv pip install -r requirements.txt -r requirements-dev.txt

# Verification gate — must pass before any phase is complete
ruff check . && black --check . && mypy . && pytest

# Tests with coverage floor (core/modules/reports/plugins)
pytest -m "not integration" --cov --cov-report=term
```

The suite is fully offline: integration tests drive a real scan pipeline against an in-process loopback mock server, so no external network is required.

---

## Project Structure

```text
IntelXtract/
├── app/          # application bootstrap
├── core/         # engine, scheduler, worker pool, correlation, risk, config, HTTP, cache, offload
├── modules/      # OSINT collectors (domain, ip, email, username, website, certificate, metadata, news)
├── plugins/      # optional third-party integrations (Wayback, VirusTotal, _template)
├── database/     # schema, migrations, repositories (targets, scans, findings, history, plugins, schedules, cases)
├── cli/          # Typer command-line interface
├── gui/          # PySide6 desktop application (pages/, viz/, bridge/, context/)
├── reports/      # report builders (HTML/PDF/JSON/CSV/MD) + Jinja2 templates
├── templates/    # report.html.j2
├── exports/      # generated reports (gitignored)
├── assets/       # logo, icons
├── config/       # settings (local, gitignored)
├── tests/        # pytest suite (unit, integration, GUI, CLI, performance)
├── docs/         # architecture, plan, brand, governance docs
└── scripts/      # build/bench helper scripts
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/Phase_Plan.md`](docs/Phase_Plan.md) | Execution plan & live status |
| [`docs/Development_Plan.md`](docs/Development_Plan.md) | Full 29-phase roadmap |
| [`docs/architecture.md`](docs/architecture.md) | System architecture (single source of truth) |
| [`docs/user_guide.md`](docs/user_guide.md) | Installation, CLI cookbook, GUI walkthrough, scan modes, report formats |
| [`docs/developer_guide.md`](docs/developer_guide.md) | Adding modules, running tests, conventions, phase-gate workflow |
| [`docs/plugin_sdk.md`](docs/plugin_sdk.md) | Plugin SDK with full working examples |
| [`docs/faq.md`](docs/faq.md) | Frequently asked questions |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Detailed troubleshooting guide |
| [`docs/Database_Schema.md`](docs/Database_Schema.md) | Database design |
| [`docs/settings.md`](docs/settings.md) | Configuration precedence & secret vault |
| [`docs/performance.md`](docs/performance.md) | Performance work & benchmarks |
| [`docs/brand/BRAND.md`](docs/brand/BRAND.md) | Visual identity & tokens |
| [`docs/coding_standards.md`](docs/coding_standards.md) | Code rules |
| [`docs/git_workflow.md`](docs/git_workflow.md) | Branch/commit/phase-gate workflow |
| [`docs/threat_model.md`](docs/threat_model.md) | Threat model |
| [`docs/privacy.md`](docs/privacy.md) | Privacy statement |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting |

---

## Responsible Use

IntelXtract operates on **publicly available information and authorized APIs only**. It performs no exploitation, credential attacks, or unauthorized access. Use it only against targets you are authorized to research, and handle collected personal data in accordance with applicable law. See [`docs/threat_model.md`](docs/threat_model.md) for the ethical boundary enforced by design.

---

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/git_workflow.md`](docs/git_workflow.md). Work proceeds one phase at a time per [`docs/Phase_Plan.md`](docs/Phase_Plan.md).

---

## License

[GPL-3.0-or-later](LICENSE) © IntelXtract contributors.