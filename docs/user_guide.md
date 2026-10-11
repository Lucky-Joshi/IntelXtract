# User Guide

Complete guide to installing, configuring, and using IntelXtract from the CLI and GUI.

---

## Installation

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- For GUI: PySide6 dependencies (usually satisfied by uv/pip)
- For PDF reports: WeasyPrint + system libraries (pango, cairo, gdk-pixbuf, fontconfig)

### From Source (Development)

```bash
git clone https://github.com/yourorg/IntelXtract
cd IntelXtract

# Create virtual environment and install dependencies
uv venv .venv
uv pip install -r requirements.txt -r requirements-dev.txt

# Run the verification gate
ruff check . && black --check . && mypy . && pytest
```

### CLI Entry Points

After installation (Phase 28+), the following commands are available:

```bash
intelxtract        # Main CLI
intelxtract-gui    # PySide6 desktop application
```

During development, run via the module entry points:

```bash
python -m cli.main          # CLI
python -m gui.main          # GUI
```

---

## Configuration

IntelXtract uses a layered configuration system (see `docs/settings.md`). Key files:

| Layer | Path | Purpose |
|-------|------|---------|
| Defaults | `core/config.py` | Built-in defaults |
| User | `~/.config/intelxtract/config.toml` | User overrides |
| Local | `.intelxtract.toml` (project root) | Project-specific |
| Environment | `INTELXTRACT_*` | Highest precedence |

### Common Settings

```toml
# paths.db_path = "~/.local/share/intelxtract/intelxtract.db"
# scan.max_workers = 8
# scan.default_timeout = 30.0
# cache.enabled = true
# cache.ttl = 300
# cache.max_size = 1024
# performance.offload_workers = 4
# network.max_connections = 100
# network.per_host_limit = 10
# network.request_timeout = 10.0
```

### API Keys (Encrypted Vault)

Keys are stored in an encrypted SQLite vault (see `docs/settings.md`):

```bash
# Store a key
intelxtract key store virustotal YOUR_API_KEY

# List stored keys (masked)
intelxtract key list

# Retrieve (for debugging)
intelxtract key get virustotal
```

Keys are referenced in modules/plugins via `requires_keys = ("virustotal",)` and accessed at runtime via `ctx.api_key("virustotal")`.

---

## CLI Cookbook

### Basic Scan

```bash
# Quick scan (DNS + HTTP for domains; Geo + RDNS for IPs)
intelxtract scan example.com

# Deep scan (all applicable modules)
intelxtract scan example.com --mode deep

# Custom module selection
intelxtract scan example.com --mode custom --modules dns,whois,ssl,http
```

### Scan Modes

| Mode | Domain Modules | IP Modules | URL Modules | Email Modules |
|------|----------------|------------|-------------|---------------|
| `quick` | dns, http | geo, rdns | headers, http_methods | email |
| `deep` | whois, dns, ssl, subdomain, http, website, certificate, news | geo, rdns, reputation | headers, tech, favicon, robots, http_methods, domain, certificate | email, breach, domain |
| `custom` | Uses deep profile, then filters by `--modules` | | | |

### Target Types

IntelXtract auto-classifies the target string:

| Type | Example | Classification Rule |
|------|---------|---------------------|
| Domain | `example.com` | Valid hostname with ≥1 dot |
| IP | `1.1.1.1` or `[2001:db8::1]` | IPv4/IPv6 address |
| URL | `https://example.com/path` | Has scheme or host+path |
| Email | `user@example.com` | `local@host` format |
| Username | `@alice` or `alice_123` | Social handle pattern |
| Hash | `d41d8cd98f00b204e9800998ecf8427e` | 32/40/64 hex chars |
| File | `report.pdf` or `/path/to/file` | Path separators or known extension |

### Output & Exit Codes

- Exit 0: Success (even if modules failed — check `ScanResult.runs`)
- Exit 1: Validation error, database error, or scan aborted
- JSON output: Use `--json` flag on commands that support it

### Reporting

```bash
# List recent scans
intelxtract history list --limit 20

# Show scan details
intelxtract history show <scan-id-or-uuid>

# Export report (formats: json, csv, md, html, pdf)
intelxtract report export <scan-ref> --format html --output report.html

# Export with specific scan UUID
intelxtract report export a1b2c3d4e5f6 --format pdf --output report.pdf
```

### Scheduled Scans

```bash
# Add recurring scan (interval)
intelxtract schedule add example.com --every 3600 --mode deep

# Add recurring scan (cron)
intelxtract schedule add example.com --cron "0 2 * * *" --mode deep

# List schedules
intelxtract schedule list

# Run due schedules once (foreground)
intelxtract schedule run

# Run scheduler daemon
intelxtract serve
```

### Case Management

Group related scans into an investigation:

```bash
# Create a case
intelxtract case create "Phishing Campaign" --description "Tracking indicators"

# Attach a scan to a case
intelxtract case add-evidence 1 --scan 42

# Attach a specific finding
intelxtract case add-evidence 1 --finding 123

# Generate combined case report
intelxtract case report 1 --format html --output case-report.html
```

### Plugin Management

```bash
# List discovered plugins
intelxtract plugin list

# Show plugin details
intelxtract plugin info wayback

# Enable/disable (persisted in DB)
intelxtract plugin enable virustotal
intelxtract plugin disable wayback
```

### Configuration Commands

```bash
# Get a value
intelxtract config get scan.max_workers

# Set a value
intelxtract config set scan.max_workers 16

# List all config
intelxtract config list
```

### Health Check

```bash
# Full system health check
intelxtract doctor
```

Checks: database connectivity, migrations, vault, config validity, module discovery, network reachability (optional).

---

## GUI Walkthrough

Launch the GUI:

```bash
python -m gui.main
# or
intelxtract-gui
```

### Main Window Layout

```
┌─────────────────────────────────────────────────────────────┐
│ IntelXtract 0.1.0a0                                    v0.1.0│
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  ☰ Nav   │              Active Page                         │
│  ▼       │                                                  │
│ ┌──────┐ │  ┌────────────────────────────────────────────┐  │
│ │Dashboard│  │                                          │  │
│ │Quick Scan│  │         Page Content                     │  │
│ │Deep Scan │  │                                          │  │
│ │Results   │  │                                          │  │
│ │Reports   │  │                                          │  │
│ │History   │  │                                          │  │
│ │Cases     │  │                                          │  │
│ │Schedules │  │                                          │  │
│ │Assistant │  │                                          │  │
│ │Plugins   │  │                                          │  │
│ │API Mgr   │  │                                          │  │
│ │Settings  │  │                                          │  │
│ │About     │  │                                          │  │
│ └──────┘ │  └────────────────────────────────────────────┘  │
├──────────┴──────────────────────────────────────────────────┤
│ Status: Ready                                    v0.1.0a0   │
└─────────────────────────────────────────────────────────────┘
```

### Pages

| Page | Purpose |
|------|---------|
| **Dashboard** | Recent scans, quick stats, launch quick/deep scan |
| **Quick Scan** | Single-field target entry, runs QUICK profile, live progress bar |
| **Deep Scan** | Target + mode selector (quick/deep/custom), module checklist, live module progress |
| **Results** | Findings table (filter by severity/module), evidence panel, correlation graph (NetworkX), risk overview |
| **Reports** | List generated reports, preview HTML, export to any format |
| **History** | Searchable scan list, double-click for details, diff two scans |
| **Cases** | Create cases, drag scans/findings into case, generate combined report |
| **Schedules** | Add/edit/remove recurring scans, cron/interval, run now button |
| **Assistant** | Chat with AI (local Ollama or remote OpenAI-compatible) — context-aware |
| **Plugins** | Discovered plugins list, enable/disable toggle, manifest viewer |
| **API Manager** | Form to store/retrieve encrypted API keys per provider |
| **Settings** | Config editor (TOML), theme toggle, paths, performance tuning |
| **About** | Version, links, license |

### Running a Scan in the GUI

1. Click **Quick Scan** or **Deep Scan** in sidebar
2. Enter target (domain, IP, URL, email, username, hash, or file path)
3. For Deep Scan: adjust mode and module checkboxes
4. Click **Start Scan** — progress appears in real time (module status chips)
5. When complete, **Results** page opens automatically
6. Use **Reports** to export

### Visualizations (Results Page)

- **Correlation Graph** — Interactive NetworkX graph (entities + edges). Pan, zoom, click nodes for details.
- **Timeline** — News/article events chronologically.
- **Risk Chart** — Category score bars + top contributing rules.
- **Severity Breakdown** — Counts by critical/high/medium/low/info.

---

## Report Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| JSON | `.json` | Canonical `ReportModel` dump — machine-readable, complete |
| CSV | `.csv` | One row per finding (severity, module, title, confidence, evidence) |
| Markdown | `.md` | Human-readable single-file report with tables |
| HTML | `.html` | Styled report with brand tokens, responsive, printable |
| PDF | `.pdf` | WeasyPrint-rendered HTML → PDF (requires system deps) |

### Report Contents

Every report includes:

1. **Header** — Brand, version, target, type, mode, timestamps
2. **Executive Summary** — Overall risk rating + top 3 findings
3. **Risk Overview** — Category scores (capped), top 12 contributing rules
4. **Findings Table** — All findings sorted by severity, with evidence
5. **Module Summary** — Finding count per module
6. **Timeline** — Dated events (news articles, scan start/end)
7. **Methodology & Evidence** — Passive-only methodology + top evidence refs

---

## Scan Modes Deep Dive

### QUICK Profile

Minimal, fast reconnaissance:

- **Domain**: `dns` (A/AAAA/CNAME/MX/TXT/SPF/DMARC), `http` (headers, status, redirect chain)
- **IP**: `geo` (ASN, ISP, country, city), `rdns` (PTR)
- **URL**: `headers`, `http_methods` (OPTIONS, TRACE check)
- **Email**: `email` (MX validation, disposable check)
- **Username**: `username` (site presence checks)
- **FILE**: `metadata` (EXIF, PDF properties, Office metadata)

Typical time: 2–5 seconds.

### DEEP Profile

Comprehensive intelligence gathering:

- **Domain**: All QUICK + `whois` (RDAP), `ssl` (cert chain, SAN, expiry), `subdomain` (crtsh, CT logs), `website` (tech stack, favicon, robots, sitemap), `certificate` (CT history), `news` (RSS/Google News)
- **IP**: All QUICK + `reputation` (abuseIPDB, greynoise if keys configured)
- **URL**: All QUICK + `tech` (Wappalyzer-style), `favicon` (hash), `robots`, `domain` (extract domain modules), `certificate`
- **Email**: All QUICK + `breach` (HaveIBeenPwned), `domain` (extract domain modules)
- **Username**: `username` (all sites in `sites.json`)

Typical time: 15–60 seconds depending on target and network.

### CUSTOM Profile

Starts from DEEP, then filters to explicit `--modules` list (CLI) or checkboxes (GUI).

---

## Module Reference

| Module | Registry Name | Target Types | Description |
|--------|---------------|--------------|-------------|
| DNS | `dns` | DOMAIN | A/AAAA/CNAME/MX/TXT/NS/SPF/DMARC via DoH |
| WHOIS/RDAP | `whois` | DOMAIN | Registrar, dates, nameservers, DNSSEC, contacts |
| SSL/TLS | `ssl` | DOMAIN | Cert chain, expiry, SAN, issuer, TLS versions |
| Subdomain | `subdomain` | DOMAIN | crt.sh CT log enumeration |
| HTTP | `http` | DOMAIN, URL | Headers, status, redirect chain, server, cookies |
| Website | `website` | DOMAIN | Tech stack, favicon hash, robots.txt, sitemap |
| Certificate | `certificate` | DOMAIN, URL | CT history, serial, issuer, related names |
| News | `news` | DOMAIN | RSS/Google News timeline for entity |
| GeoIP | `geo` | IP | ASN, ISP, org, country, region, city, coords |
| Reverse DNS | `rdns` | IP | PTR records, hostname matches |
| Reputation | `reputation` | IP | AbuseIPDB, GreyNoise (key-gated) |
| Email | `email` | EMAIL | Syntax, MX, disposable detection, domain extraction |
| Breach | `breach` | EMAIL | HIBP breach lookup (key-gated) |
| Username | `username` | USERNAME | 100+ site presence checks via `sites.json` |
| Metadata | `metadata` | FILE | PDF props, image EXIF, Office core props |

---

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `Module SKIPPED: missing api key` | `requires_keys` not configured | `intelxtract key store <name> <value>` |
| `ScanEngine: module discovery failed` | Import error in modules/ | Check `python -c "import modules.domain.dns"` |
| `WeasyPrint not installed` | PDF export fallback to HTML | Install weasyprint + system deps |
| `database is locked` | Concurrent writers | Use single process; check `paths.db_path` |
| `migration failed` | Schema version mismatch | `intelxtract db migrate --force` (dev only) |

See `docs/troubleshooting.md` for detailed troubleshooting.

---

## Responsible Use

IntelXtract operates on **publicly available information and authorized APIs only**. It performs no exploitation, credential attacks, or unauthorized access. Use it only against targets you are authorized to research, and handle collected personal data in accordance with applicable law. See `docs/threat_model.md` for the ethical boundary enforced by design.