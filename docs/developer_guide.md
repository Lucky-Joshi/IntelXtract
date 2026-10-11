# Developer Guide

Guide for contributing to IntelXtract: adding modules, writing tests, code conventions, and the phase-gate workflow.

---

## Repository Structure

```
IntelXtract/
├── app/                    # Application bootstrap (empty, reserved)
├── core/                   # Engine, scheduler, worker pool, correlation, risk, config, HTTP, cache, offload
├── modules/                # OSINT collectors (domain, ip, email, username, website, certificate, metadata, news)
├── plugins/                # Optional third-party integrations (Wayback, VirusTotal, _template)
├── database/               # Schema, migrations, repositories (targets, scans, findings, history, plugins, schedules, cases)
├── cli/                    # Typer command-line interface
├── gui/                    # PySide6 desktop application (pages/, viz/, bridge/, context/)
├── reports/                # Report builders (HTML/PDF/JSON/CSV/MD) + Jinja2 templates
├── templates/              # report.html.j2
├── exports/                # Generated reports (gitignored)
├── assets/                 # Logo, icons
├── config/                 # Local settings (gitignored)
├── tests/                  # pytest suite (unit, integration, GUI, CLI, performance)
├── docs/                   # Architecture, plan, brand, governance docs
└── scripts/                # Build/bench helper scripts
```

---

## Adding a Core Module

### 1. Choose the Category

Create the module file under the appropriate package:

```
modules/
├── domain/       # Domain-targeted collectors (dns, whois, ssl, subdomain, http, website, certificate, news)
├── ip/           # IP-targeted collectors (geo, rdns, reputation)
├── email/        # Email-targeted collectors (collector, breach, mx, validation, gravatar)
├── username/     # Username collectors (collector, enrichment, social)
├── website/      # Website/URL collectors (headers, tech, favicon, robots, http_methods)
├── certificate/  # Certificate transparency (collector, details, tls_probe, transparency)
├── metadata/     # File metadata (pdf, image, office, collector)
└── news/         # News collectors (collector, feeds, rss, timeline)
```

### 2. Implement the Module

Create `modules/<category>/<name>.py`:

```python
"""Short description of what this module collects."""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from modules.base import BaseModule


class MyModule(BaseModule):
    """One-line docstring describing the collector."""

    name = "mymodule"              # Unique registry name (lowercase, no spaces)
    target_types = (TargetType.DOMAIN,)  # Tuple of TargetType this module handles
    requires_keys = ()             # Tuple of api_keys.* names required (empty = no key needed)
    description = "What this module collects."
    timeout = 30.0                 # Optional per-module timeout override
    retries = 2                    # Optional retry count for transient failures

    def validate(self, target: str) -> bool:
        """Return True if target is acceptable for this module."""
        # BaseModule validates non-empty; add domain-specific checks if needed
        return super().validate(target)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        # 1. Use ctx.http for all network I/O (retries, pacing, cache, ETag)
        #    await ctx.http.get_json(url, params={...}, headers={...})
        #    await ctx.http.get_text(url)
        #    await ctx.http.request(method, url, ...)

        # 2. Access API keys via ctx.api_key("keyname") → str | None

        # 3. Read config via ctx.config.get("section.key")

        # 4. Use ctx.cached(key, async_factory, ttl=300) for memoization

        # 5. Offload blocking work: await ctx.to_thread(blocking_func, arg)

        # 6. Build findings with make_finding()
        finding = make_finding(
            module=self.name,
            title="Descriptive title for this finding",
            data={"key": "structured data for correlation/risk"},
            severity=Severity.INFO,           # INFO, LOW, MEDIUM, HIGH, CRITICAL
            confidence=0.8,                   # 0.0–1.0
            evidence="Human-readable evidence string",
        )

        # 7. Return ModuleResult
        return ModuleResult(
            data={"summary": "optional structured output"},
            findings=(finding,),
        )
```

### 3. Register the Module

Modules are auto-discovered via `ModuleRegistry.discover("modules.domain")` (etc.) in `cli/main.py:_engine_modules()`. No manual registration needed — just ensure:

- The class inherits `BaseModule`
- `name` is a non-empty string (unique across all modules)
- `target_types` is a tuple of `TargetType`
- The module file is imported by its package's `__init__.py` (or is a submodule walked by `pkgutil`)

### 4. Add to Input Engine Profiles

Edit `core/input_engine.py` to include your module in the selection maps:

```python
_QUICK_MODULES = {
    TargetType.DOMAIN: ("dns", "http", "mymodule"),  # Add to QUICK if appropriate
    ...
}

_DEEP_MODULES = {
    TargetType.DOMAIN: (
        "whois", "dns", "ssl", "subdomain", "http",
        "website", "certificate", "news", "mymodule"
    ),
    ...
}
```

### 5. Write Tests

Create `tests/modules/<category>/test_<name>.py`:

```python
"""Tests for mymodule."""

from __future__ import annotations

import pytest

from core.constants import TargetType
from core.engine import ModuleContext
from core.models import make_finding
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.domain.mymodule import MyModule


@pytest.mark.asyncio
async def test_mymodule_basic() -> None:
    client = FakeHttpClient()
    client.stub("https://api.example.com/endpoint", body={"key": "value"})

    config = make_module_config()
    ctx = make_module_context(config, http=client)

    module = MyModule()
    result = await module.run("example.com", ctx)

    assert result.findings
    finding = result.findings[0]
    assert finding.module == "mymodule"
    assert finding.severity is not None
    assert finding.data.get("key") == "value"


@pytest.mark.asyncio
async def test_mymodule_requires_key() -> None:
    """Module is skipped when required key is missing."""
    module = MyModule()
    module.requires_keys = ("my_api",)

    config = make_module_config()  # No api_keys.my_api set
    ctx = make_module_context(config)

    # The planner in ScanEngine checks requires_keys before running;
    # this test validates the module's metadata
    assert "my_api" in module.requires_keys
```

### 6. Run the Test Suite

```bash
# Run just your module tests
pytest tests/modules/domain/test_mymodule.py -v

# Run full suite with coverage
pytest -m "not integration" --cov --cov-report=term
```

---

## Test Conventions

### Fixtures (`tests/modules/fakes.py`)

| Fixture / Helper | Purpose |
|---|---|
| `make_module_config()` | Minimal `Config` with test defaults |
| `make_module_context(config, http=None, cache=None)` | `ModuleContext` with optional injected `FakeHttpClient` |
| `FakeHttpClient` | In-memory HTTP stub: `.stub(url, body=..., status=200, headers={})` |
| `DummyModule(name, target_types, findings)` | Minimal module for engine integration tests |

### Common Patterns

```python
# Stubbing HTTP responses
client = FakeHttpClient()
client.stub("https://api.example.com/data", body={"result": "ok"})

# Testing with cache
from core.cache import AsyncTTLCache
cache = AsyncTTLCache(max_size=100, default_ttl=60.0)
ctx = make_module_context(config, http=client, cache=cache)

# Testing ctx.cached
async def factory():
    return {"computed": "value"}

val1 = await ctx.cached("mykey", factory, ttl=60)
val2 = await ctx.cached("mykey", factory, ttl=60)
assert val1 == val2  # Factory ran once
```

### Integration Tests

For end-to-end tests using the real scan pipeline against a loopback mock server, see `tests/integration/test_offline_scan.py`. Key patterns:

```python
# aiohttp test server serving mock endpoints
# ModuleContext with endpoint overrides via config:
#   config.set("dns.endpoint", "http://127.0.0.1:PORT/dns-query")
#   config.set("whois.endpoint", "http://127.0.0.1:PORT/rdap/domain/{name}")
# ...
```

### GUI Tests (pytest-qt)

```python
def test_navigation(qtbot, main_window):
    qtbot.mouseClick(main_window.nav_buttons["quick_scan"], Qt.MouseButton.LeftButton)
    assert main_window.stacked.currentWidget() is main_window.pages["quick_scan"]
```

### Performance Budget Tests

```python
def test_cache_budget():
    # 200k operations in < 5 seconds
    assert duration < 5.0
```

---

## Code Conventions

### Type Hints

- All public functions/classes must have type hints
- Use `from __future__ import annotations` (PEP 563)
- Prefer `Sequence`/`Mapping`/`Iterable` over `list`/`dict` in signatures
- Use `TypeVar`/`ParamSpec` for generics (see `modules/base.py`)

### Async

- All I/O is async; no blocking calls in async functions (ruff ASYNC240)
- Use `ctx.to_thread()` for CPU-bound or blocking stdlib calls
- `ctx.cached()` factory must be `Callable[[], Awaitable[T]]`

### Error Handling

- **Fail-soft**: Module failures → `ModuleRun.status = FAILED/TIMEOUT`; scan continues
- **Plugin load errors**: Recorded in `PluginInfo.error`; never crash startup
- **Risk/Correlation exceptions**: Caught, logged, `None` result; scan continues
- **Validation errors**: Raised early (`ValidationError`) for bad input

### Naming

- Modules: `snake_case` file, `PascalCase` class, `name = "kebab-case"` registry name
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Test files: `test_<name>.py`, test functions: `test_<behavior>`

### Imports

- Standard library → third-party → local (`core.`, `modules.`, `database.`, etc.)
- No wildcard imports
- Relative imports within a package; absolute from root for cross-package

### Linting / Formatting

```bash
ruff check .          # Lint
black --check .       # Format check
mypy .                # Type check
pytest                # Tests
```

All must pass before committing (pre-commit hook runs `ruff` + `black --check`).

### Security

- No secrets in code (ruff S105/S106/S107)
- API keys only via encrypted vault (`core/vault.py`)
- Parameterized SQL only (ruff S608)
- No `eval`/`exec`/dynamic code execution

---

## Phase-Gate Workflow

Each phase follows this process:

1. **Implement** the sub-phases in order (S27.1, S27.2, …)
2. **Verify** locally: `ruff check . && black --check . && mypy . && pytest`
3. **Update docs**: `docs/Phase_Plan.md` checkboxes, `CHANGELOG.md`
4. **Commit**: `git add -A && git commit -m "feat(phase-XX): <summary>"`
5. **Do not push** — pushing is user-owned

Commit message format:
```
feat(phase-XX): short summary

- Bullet 1
- Bullet 2
- ...
```

---

## Common Tasks

### Run a Single Test

```bash
pytest tests/modules/domain/test_dns.py::test_dns_a_record -v
```

### Run with Coverage

```bash
pytest --cov=core --cov=modules --cov=reports --cov=plugins --cov-report=term-missing
```

### Type Check a Single File

```bash
mypy core/engine.py
```

### Debug a Test

```bash
pytest tests/modules/domain/test_dns.py -v -s --tb=long
```

### Add a Dependency

1. Add to `requirements.txt` (runtime) or `requirements-dev.txt` (dev)
2. Run `uv pip install -r requirements.txt -r requirements-dev.txt`
3. Update `pyproject.toml` if it's a tool dependency

---

## Architecture Decision Records

Key decisions are documented inline in the relevant source files. For the big picture, see `docs/architecture.md`.

---

## Useful Commands

```bash
# Full gate (run before every phase commit)
ruff check . && black --check . && mypy . && pytest -p no:cacheprovider -rN

# Quick sanity check
pytest tests/modules/ -q

# Update Phase_Plan.md checkboxes after completing a sub-phase
# Edit docs/Phase_Plan.md, flip [ ] → [x] for the item

# View current phase status
grep -A 20 "Phase 27" docs/Phase_Plan.md
```