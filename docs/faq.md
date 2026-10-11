# Frequently Asked Questions

## General

### What is IntelXtract?

IntelXtract is an AI-powered OSINT automation platform that collects, normalizes, correlates, analyzes, visualizes, and reports publicly available intelligence from many sources — WHOIS, DNS, SSL, HTTP, IP, email, usernames, certificate transparency, archives, news, and more — inside one unified interface instead of fifteen browser tabs.

### What are the system requirements?

- Python 3.13+
- uv (recommended) or pip
- For GUI: PySide6 (installed via requirements)
- For PDF reports: WeasyPrint + system libraries (pango, cairo, gdk-pixbuf, fontconfig)

### Is IntelXtract free / open source?

Yes, IntelXtract is licensed under GPL-3.0-or-later. See `LICENSE` for details.

### Does IntelXtract perform active exploitation?

**No.** IntelXtract operates on **publicly available information and authorized APIs only**. It performs no exploitation, credential attacks, or unauthorized access. Use it only against targets you are authorized to research, and handle collected personal data in accordance with applicable law.

---

## Installation & Setup

### How do I install IntelXtract?

```bash
git clone https://github.com/yourorg/IntelXtract
cd IntelXtract
uv venv .venv
uv pip install -r requirements.txt -r requirements-dev.txt
```

### How do I run the CLI?

```bash
python -m cli.main scan example.com --mode deep
# or after Phase 28 packaging:
intelxtract scan example.com --mode deep
```

### How do I run the GUI?

```bash
python -m gui.main
# or after Phase 28 packaging:
intelxtract-gui
```

### How do I verify my installation?

```bash
ruff check . && black --check . && mypy . && pytest
# or just:
intelxtract doctor
```

---

## Configuration

### Where are config files located?

| Layer | Path |
|-------|------|
| User | `~/.config/intelxtract/config.toml` |
| Project | `.intelxtract.toml` (repo root) |
| Environment | `INTELXTRACT_*` variables |

See `docs/settings.md` for the full precedence order.

### How do I set an API key?

```bash
intelxtract key store virustotal YOUR_API_KEY
```

Keys are encrypted at rest in the SQLite vault (see `core/vault.py`).

### How do I change the database path?

```toml
# In config.toml or .intelxtract.toml
paths.db_path = "~/.local/share/intelxtract/intelxtract.db"
```

Or override via CLI: `intelxtract scan example.com --db /path/to/db.sqlite`

---

## Scanning

### What scan modes are available?

| Mode | Use Case |
|------|----------|
| `quick` | Fast reconnaissance (DNS + HTTP for domains; Geo + RDNS for IPs) |
| `deep` | Comprehensive intelligence (all applicable modules) |
| `custom` | Deep profile filtered to explicit module list |

### Why was my module skipped?

Common reasons (shown in `ScanResult.runs` with `status: "skipped"`):

1. **Target type mismatch** — Module doesn't support the classified target type
2. **Missing API key** — Module declares `requires_keys` but `api_keys.<name>` is not configured
3. **Validation failed** — `module.validate(target)` returned `False`

### How do I run only specific modules?

```bash
intelxtract scan example.com --mode custom --modules dns,whois,ssl,http
```

In the GUI: Deep Scan page → uncheck modules you don't want.

### What target types are supported?

| Type | Example | Notes |
|------|---------|-------|
| Domain | `example.com` | Auto-punycoded |
| IP | `1.1.1.1` or `[2001:db8::1]` | IPv6 requires brackets with port |
| URL | `https://example.com/path` | Scheme defaults to https |
| Email | `user@example.com` | Validates host part |
| Username | `@alice` or `alice_123` | Social handle pattern |
| Hash | `d41d8cd98f00b204e9800998ecf8427e` | MD5/SHA1/SHA256 hex |
| File | `report.pdf` or `/path/file` | Path separators or known extension |

---

## Reports

### What report formats are supported?

| Format | Extension | Notes |
|--------|-----------|-------|
| JSON | `.json` | Complete canonical model |
| CSV | `.csv` | One row per finding |
| Markdown | `.md` | Human-readable |
| HTML | `.html` | Styled, brand-aware, printable |
| PDF | `.pdf` | WeasyPrint (falls back to HTML if unavailable) |

### How do I export a report?

```bash
# From a scan ID or UUID
intelxtract report export 42 --format html --output report.html
intelxtract report export a1b2c3d4e5f6 --format pdf --output report.pdf
```

### Can I generate a report for a case (multiple scans)?

```bash
intelxtract case report 1 --format html --output case-report.html
```

---

## Scheduled Scans

### How do I set up a recurring scan?

```bash
# Every hour
intelxtract schedule add example.com --every 3600 --mode deep

# Daily at 2 AM (cron)
intelxtract schedule add example.com --cron "0 2 * * *" --mode deep
```

### How do I run the scheduler?

```bash
# Run due scans once (foreground)
intelxtract schedule run

# Run as daemon (polls every 30s)
intelxtract serve
```

---

## Plugins

### How do I create a plugin?

Copy `plugins/_template/` to a new directory, edit `manifest.json` and `plugin.py`. See `docs/plugin_sdk.md` for the full guide.

### Why isn't my plugin loading?

Run `intelxtract plugin list` — plugins with errors show the reason in the `error` column. Common issues:

- Invalid `manifest.json` (JSON syntax, missing required fields)
- `api_version` > current SDK version (1)
- No `PluginBase` subclass found in `plugin.py`
- Import error in `plugin.py`

### How do I enable a plugin?

```bash
intelxtract plugin enable myplugin
```

State is persisted in the database.

---

## GUI

### The GUI won't start — what's wrong?

1. Ensure PySide6 is installed: `uv pip install PySide6==6.10.3`
2. On Linux, you may need system packages: `qt6-base`, `libxcb-*`
3. Run with `QT_DEBUG_PLUGINS=1 python -m gui.main` to diagnose

### How do I switch themes?

Settings page → Theme toggle (Light/Dark/System). Persisted in config.

---

## Development

### How do I run tests?

```bash
# Full suite with coverage
pytest -m "not integration" --cov --cov-report=term

# Unit tests only
pytest tests/modules/ tests/core/ tests/database/ -q

# GUI tests (requires pytest-qt)
pytest tests/gui/ -q

# Integration tests (offline mock server)
pytest tests/integration/ -q
```

### How do I add a new module?

See `docs/developer_guide.md#adding-a-core-module`.

### What's the phase-gate workflow?

Each phase ends with: `ruff check . && black --check . && mypy . && pytest` — all must pass before commit. See `docs/git_workflow.md`.

---

## Troubleshooting

See `docs/troubleshooting.md` for detailed troubleshooting guides.