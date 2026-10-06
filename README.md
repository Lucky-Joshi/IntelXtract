# IntelXtract

<p align="center">
  <img src="assets/logo.svg" alt="IntelXtract — OSINT Automation Platform" width="360">
</p>

**AI-powered OSINT automation & intelligence platform.**

IntelXtract collects, normalizes, correlates, analyzes, visualizes, and
reports publicly available intelligence from many sources — WHOIS, DNS, SSL,
HTTP, IP, email, usernames, certificate transparency, archives, news, and
more — inside one unified interface instead of fifteen browser tabs.

> **Status: pre-alpha.** The project is being built phase-by-phase per the
> execution plan. Core engine, CLI, GUI, and modules are not yet implemented.
> See [`docs/Phase_Plan.md`](docs/Phase_Plan.md) for current progress and
> [`docs/Development_Plan.md`](docs/Development_Plan.md) for the full roadmap.

## Why IntelXtract

Most OSINT tools aggregate lookups. IntelXtract is built around four
principles:

- **Automation** — one target in, a full multi-module scan out (quick, deep,
  custom, batch).
- **Correlation** — findings are linked into entities and relationship
  graphs, not left as isolated facts.
- **Visualization** — relationship graphs, timelines, maps, and risk charts.
- **Reporting** — polished HTML/PDF/JSON/CSV/Markdown reports with executive
  summary, evidence, and methodology.

## Planned capabilities

| Area | Examples |
|------|----------|
| Domain | WHOIS, DNS/SPF/DKIM/DMARC, subdomains, SSL, headers, robots/sitemap |
| IP | ASN/ISP/geolocation, reverse DNS, reputation (authorized sources) |
| Website | Server/tech fingerprinting, cookies, methods, favicon hash |
| Email | Validation, MX, disposable detection, permitted breach checks |
| Username | Presence checks + public profile enrichment |
| Certificate | Chain, TLS versions, certificate transparency history |
| Metadata | PDF, image EXIF, Office document properties |
| News | RSS/news timeline for entities |
| Intelligence | Correlation graph, risk scoring, scheduled scans, plugins |

## Architecture

```text
CLI / GUI (PySide6)
        │
  Core Scan Engine ── input parser · scheduler · worker pool
        │
  OSINT Modules (async, independent)
        │
  Correlation Engine → Risk Engine
        │
  SQLite / PostgreSQL
        │
  HTML · PDF · JSON · CSV · Markdown reports
```

Details: [`docs/architecture.md`](docs/architecture.md),
[`docs/internal_architecture.md`](docs/internal_architecture.md),
[`docs/Scan_Engine_Workflow.md`](docs/Scan_Engine_Workflow.md).

## Development setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv .venv
uv pip install -r requirements.txt -r requirements-dev.txt

# verification gate — must pass before any phase is complete
ruff check . && black --check . && mypy . && pytest
```

End-user installation and the `intelxtract` CLI arrive with Phase 4;
packaging with Phase 28.

## Project structure

```text
IntelXtract/
├── app/          # application bootstrap
├── core/         # engine, scheduler, worker pool, correlation, risk, config
├── modules/      # OSINT collectors (domain, ip, email, username, website, …)
├── plugins/      # optional third-party integrations
├── database/     # schema, migrations, repositories
├── cli/          # Typer command-line interface
├── gui/          # PySide6 desktop application
├── reports/      # report builders
├── templates/    # Jinja2 report templates
├── exports/      # generated reports (gitignored)
├── assets/       # logo, icons
├── config/       # settings (local, gitignored)
├── tests/        # pytest suite
├── docs/         # architecture, plan, brand, governance docs
└── scripts/      # build/bench helper scripts
```

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/Phase_Plan.md`](docs/Phase_Plan.md) | Execution plan & live status |
| [`docs/Development_Plan.md`](docs/Development_Plan.md) | Full 29-phase roadmap |
| [`docs/architecture.md`](docs/architecture.md) | System architecture |
| [`docs/Database_Schema.md`](docs/Database_Schema.md) | Database design |
| [`docs/brand/BRAND.md`](docs/brand/BRAND.md) | Visual identity & tokens |
| [`docs/coding_standards.md`](docs/coding_standards.md) | Code rules |
| [`docs/git_workflow.md`](docs/git_workflow.md) | Branch/commit/phase-gate workflow |
| [`docs/threat_model.md`](docs/threat_model.md) | Threat model |
| [`docs/privacy.md`](docs/privacy.md) | Privacy statement |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting |

## Responsible use

IntelXtract operates on **publicly available information and authorized
APIs only**. It performs no exploitation, credential attacks, or
unauthorized access. Use it only against targets you are authorized to
research, and handle collected personal data in accordance with applicable
law. See [`docs/threat_model.md`](docs/threat_model.md) for the ethical
boundary enforced by design.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`docs/git_workflow.md`](docs/git_workflow.md). Work proceeds one phase at
a time per [`docs/Phase_Plan.md`](docs/Phase_Plan.md).

## License

[GPL-3.0-or-later](LICENSE) © IntelXtract contributors.
