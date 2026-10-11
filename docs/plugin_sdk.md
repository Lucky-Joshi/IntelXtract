# IntelXtract Plugin SDK

Plugins are self-contained collectors that run through the same scan pipeline as the built-in modules. Drop a directory under `plugins/`, and IntelXtract discovers, validates, loads, and (when enabled and applicable) runs it.

The reference implementations live in [`plugins/Wayback/`](../plugins/Wayback) and [`plugins/VirusTotal/`](../plugins/VirusTotal). A copy-me skeleton is in [`plugins/_template/`](../plugins/_template).

---

## Layout

```
plugins/
  YourPlugin/
    manifest.json   # required for discovery + validation
    plugin.py       # entry point (configurable via manifest.entry_point)
    requirements    # optional free-form notes/deps for your own reference
```

Discovery is **fail-soft**: a plugin that fails manifest validation, import, or class lookup is recorded with an error and simply skipped — it never prevents the application from starting or other plugins from running.

---

## `manifest.json`

Validated against the SDK schema (`core.plugin_loader.MANIFEST_SCHEMA`).

| Field           | Type            | Required | Notes                                                              |
|-----------------|-----------------|----------|--------------------------------------------------------------------|
| `name`          | string          | no*      | Registry name; must be non-empty. Defaults to the directory name.  |
| `version`       | string          | no*      | Plugin version (e.g. `1.0.0`). Defaults to class `version`.        |
| `api_version`   | integer ≥ 1     | no       | SDK version the plugin targets. Must be ≤ `PLUGIN_API_VERSION` (1). |
| `author`        | string          | no       | Author/owner.                                                      |
| `description`   | string          | no       | One-line summary shown by `intelxtract plugin info`.              |
| `entry_point`   | relative string | no       | Module to import (default `plugin.py`); must stay inside the dir.  |
| `target_types`  | string[]        | no       | Target kinds it applies to (`domain`, `ip`, `url`, `email`, `username`, `hash`, `file`, `unknown`). Defaults to class `target_types`. |
| `required_keys` | string[]        | no       | `api_keys.*` names that must be configured before it runs.         |

\* Fields are optional in the manifest; the plugin class is the source of truth. Manifest values override class attributes when present.

Unknown keys are tolerated for forward compatibility. Invalid known fields make the manifest invalid and the plugin is reported with the reason.

`api_version` is a compatibility gate: a plugin declaring a newer SDK than the running application refuses to load (recorded, not fatal).

---

## `plugin.py`

```python
from typing import Any
from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from core.plugin_loader import PluginBase


class MyPlugin(PluginBase):
    name = "myplugin"
    version = "1.0.0"
    description = "What it does"
    target_types = (TargetType.DOMAIN,)
    requires_keys = ()          # e.g. ("my_api",)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        ...
```

- You may declare metadata in the class, in `manifest.json`, or both; manifest values win when present.
- Return a `ModuleResult`. Anything else is normalized for you: mappings become `data`, and any `findings`/`records`/`title`-shaped content is parsed into `Finding` objects (see `core.models.parse_findings`).
- Prefer `make_finding(...)` so findings get a stable `content_hash` for deduplication.

### The run context (`ctx`)

| Access                | Purpose                                                   |
|-----------------------|-----------------------------------------------------------|
| `ctx.http`            | Shared `HttpClient` — `get_json`, `get_text`, `get`, `request` (retries transient errors). Never `None` during a scan. |
| `ctx.api_key(name)`   | Returns `api_keys.<name>` from config, or `None`.          |
| `ctx.config.get(key)` | Layered configuration lookup.                              |
| `ctx.cache`           | Shared async TTL cache (`AsyncTTLCache`).                  |
| `ctx.logger`          | Structured logger.                                         |
| `ctx.scan_id`         | Current scan id.                                           |
| `ctx.target_type`     | Classified `TargetType`.                                   |
| `ctx.to_thread(fn, *args, **kwargs)` | Run blocking callable off the event loop. |
| `ctx.cached(key, factory, ttl?)` | Memoize async factory across scans. |

### Failure behavior

- Raise, or return a finding with `Severity.INFO` — either way the engine records a per-module status; a raised exception fails only that module's run, never the scan. Example plugins catch network errors and report an "unavailable" finding rather than raising.

---

## CLI

```bash
intelxtract plugin list                 # discovered plugins + errors + enabled state
intelxtract plugin info wayback         # manifest details, source, target types
intelxtract plugin enable virustotal    # persisted in the database
intelxtract plugin disable wayback
```

Enable/disable state is persisted in the `plugins` table; use `PluginRegistry.apply_state(...)` to hydrate it at load time.

---

## Running through the engine

`PluginRegistry.engine_modules()` returns `PluginModuleAdapter` instances that satisfy the engine's module contract, so plugins and core collectors are indistinguishable to `ScanEngine`:

```python
from core.plugin_loader import PluginRegistry
from core.engine import ScanEngine
from core.config import load_config
from core.constants import ScanMode

registry = PluginRegistry(plugins_dir="plugins")
registry.discover()
registry.apply_state({"wayback": True, "virustotal": False})

config = load_config()
engine = ScanEngine(config, modules=registry.engine_modules())
result = await engine.scan("example.com", mode=ScanMode.DEEP)
```

---

## Testing your plugin

Use the fakes on the test path to run your plugin offline:

```python
from fakes import FakeHttpClient, make_module_config, make_module_context

client = FakeHttpClient()
client.stub("https://example/api", body={"ok": True})
ctx = make_module_context(make_module_config(), http=client)
result = await MyPlugin().run("example.com", ctx)
assert result.findings
```

---

## Reference: `plugins/Wayback/`

### `manifest.json`

```json
{
  "name": "wayback",
  "version": "1.0.0",
  "api_version": 1,
  "author": "IntelXtract",
  "description": "Wayback Machine CDX archive history for a domain (no key required).",
  "entry_point": "wayback.py",
  "target_types": ["domain"],
  "required_keys": []
}
```

### `wayback.py`

```python
"""Wayback Machine CDX plugin — living reference for the Plugin SDK.

Queries the public Web Archive CDX API for captures of a domain and reports
the archive span. No API key is required, so this plugin runs through the same
engine pipeline as core collectors with nothing but network access.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from core.plugin_loader import PluginBase

CDX_URL = "https://web.archive.org/cdx/search/cdx"
MAX_CAPTURES = 200


class WaybackPlugin(PluginBase):
    """Report the Wayback Machine capture history for a domain."""

    name = "wayback"
    version = "1.0.0"
    author = "IntelXtract"
    description = "Wayback Machine CDX archive history for a domain."
    target_types = (TargetType.DOMAIN,)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        try:
            rows = await ctx.http.get_json(
                CDX_URL,
                params={
                    "url": target,
                    "output": "json",
                    "collapse": "timestamp:6",
                    "limit": str(MAX_CAPTURES),
                    "fl": "timestamp,original,statuscode",
                },
            )
        except Exception as exc:  # network/HTTP failures are non-fatal
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "Wayback: archive lookup unavailable",
                        {"target": target, "error": str(exc)},
                        severity=Severity.INFO,
                        confidence=0.3,
                        evidence=f"CDX request failed: {exc}",
                    ),
                )
            )

        captures = _captures(rows)
        if not captures:
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "Wayback: no archived captures",
                        {"target": target},
                        severity=Severity.INFO,
                        confidence=0.9,
                        evidence="CDX returned no capture rows",
                    ),
                )
            )

        oldest, newest = captures[0], captures[-1]
        return ModuleResult(
            data={"count": len(captures), "captures": captures},
            findings=(
                make_finding(
                    self.name,
                    f"Wayback: {len(captures)} archived capture(s)",
                    {
                        "count": len(captures),
                        "oldest": oldest["timestamp"],
                        "newest": newest["timestamp"],
                    },
                    severity=Severity.INFO,
                    confidence=0.9,
                    evidence=f"{oldest['timestamp']} .. {newest['timestamp']}",
                ),
            ),
        )


def _captures(rows: Any) -> list[dict[str, str]]:
    """Normalize a CDX response (header row + data rows) into dicts."""
    if not isinstance(rows, list) or not rows:
        return []
    header: list[str] = []
    body = rows
    if isinstance(rows[0], list):
        header = [str(column) for column in rows[0]]
        body = rows[1:]
    captures: list[dict[str, str]] = []
    for index, row in enumerate(body):
        if isinstance(row, dict):
            captures.append({str(k): str(v) for k, v in row.items()})
        elif isinstance(row, list):
            captures.append(
                {
                    header[i] if i < len(header) else str(index): str(value)
                    for i, value in enumerate(row)
                }
            )
    return captures


PLUGIN = WaybackPlugin
```

---

## Reference: `plugins/VirusTotal/`

### `manifest.json`

```json
{
  "name": "virustotal",
  "version": "1.0.0",
  "api_version": 1,
  "author": "IntelXtract",
  "description": "VirusTotal domain reputation report (requires api key 'virustotal').",
  "entry_point": "virustotal.py",
  "target_types": ["domain"],
  "required_keys": ["virustotal"]
}
```

### `virustotal.py`

```python
"""VirusTotal domain report plugin — living reference for the Plugin SDK.

Key-gated example: declares ``required_keys = ("virustotal",)`` so the engine
planner skips it unless an ``api_keys.virustotal`` value is configured. When it
does run it turns VirusTotal's ``last_analysis_stats`` into a severity-graded
finding.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from core.plugin_loader import PluginBase

VT_URL = "https://www.virustotal.com/api/v3/domains/{target}"


class VirusTotalPlugin(PluginBase):
    """Report VirusTotal reputation detections for a domain."""

    name = "virustotal"
    version = "1.0.0"
    author = "IntelXtract"
    description = "VirusTotal domain reputation report."
    target_types = (TargetType.DOMAIN,)
    requires_keys = ("virustotal",)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        api_key = ctx.api_key("virustotal")
        if not api_key:
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "VirusTotal: not configured",
                        {"target": target},
                        severity=Severity.INFO,
                        confidence=0.2,
                        evidence="missing api key 'virustotal'",
                    ),
                )
            )
        try:
            payload = await ctx.http.get_json(
                VT_URL.format(target=target),
                headers={"x-apikey": api_key},
            )
        except Exception as exc:
            return ModuleResult(
                findings=(
                    make_finding(
                        self.name,
                        "VirusTotal: lookup unavailable",
                        {"target": target, "error": str(exc)},
                        severity=Severity.INFO,
                        confidence=0.3,
                        evidence=f"VirusTotal request failed: {exc}",
                    ),
                )
            )
        attributes = ((payload or {}).get("data") or {}).get("attributes") or {}
        stats = attributes.get("last_analysis_stats") or {}
        malicious = _int(stats.get("malicious"))
        suspicious = _int(stats.get("suspicious"))
        total = sum(_int(value) for value in stats.values())
        severity = (
            Severity.CRITICAL
            if malicious >= 5
            else (
                Severity.HIGH
                if malicious >= 1
                else Severity.MEDIUM if suspicious else Severity.INFO
            )
        )
        return ModuleResult(
            data={"stats": stats, "total_engines": total},
            findings=(
                make_finding(
                    self.name,
                    f"VirusTotal: {malicious} malicious / {suspicious} suspicious detection(s)",
                    {
                        "malicious": malicious,
                        "suspicious": suspicious,
                        "harmless": _int(stats.get("harmless")),
                        "undetected": _int(stats.get("undetected")),
                    },
                    severity=severity,
                    confidence=0.8,
                    evidence=f"{malicious} malicious of {total} engine(s)",
                ),
            ),
        )


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


PLUGIN = VirusTotalPlugin
```

---

## Skeleton: `plugins/_template/`

### `manifest.json`

```json
{
  "name": "example",
  "version": "0.1.0",
  "api_version": 1,
  "author": "Your Name",
  "description": "One-line description of what this plugin collects.",
  "entry_point": "plugin.py",
  "target_types": ["domain"],
  "required_keys": []
}
```

### `plugin.py`

```python
"""Example IntelXtract plugin (copy this directory to start a new plugin).

Rename the directory, update ``manifest.json``, and implement :meth:`run`.
Return a :class:`core.models.ModuleResult`; the engine records its findings
and stores its ``data`` exactly like a core collector.
"""

from __future__ import annotations

from typing import Any

from core.constants import Severity, TargetType
from core.models import ModuleResult, make_finding
from core.plugin_loader import PluginBase


class ExamplePlugin(PluginBase):
    """Replace this docstring with what the plugin does."""

    name = "example"
    version = "0.1.0"
    author = "Your Name"
    description = "One-line description of what this plugin collects."
    target_types = (TargetType.DOMAIN,)
    # Add ``requires_keys = ("my_api",)`` for key-gated plugins; the engine then
    # skips the plugin until ``api_keys.my_api`` is configured.

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        # ``ctx`` gives you the shared cache, logger, config, and HTTP client:
        #   await ctx.http.get_json(url, params={...}, headers={...})
        #   ctx.api_key("my_api")  -> str | None
        #   ctx.config.get("my.section.key")
        return ModuleResult(
            data={"target": target},
            findings=(
                make_finding(
                    self.name,
                    f"Example: reached {target}",
                    {"target": target},
                    severity=Severity.INFO,
                    confidence=0.5,
                    evidence="replace with real evidence",
                ),
            ),
        )


PLUGIN = ExamplePlugin
```

---

## Versioning

Bump `api_version` only when the plugin relies on a newer SDK. The current SDK version is `core.constants.PLUGIN_API_VERSION` (currently `1`).

---

## Best Practices

1. **Always handle network failures gracefully** — return an `INFO` finding with the error as evidence rather than raising.
2. **Use `make_finding`** — ensures stable `content_hash` for deduplication.
3. **Declare `requires_keys`** — the planner will skip the plugin automatically when keys are missing.
4. **Keep `run` pure-async** — use `ctx.http` for all I/O; offload blocking work via `ctx.to_thread()`.
5. **Use `ctx.cached()`** — memoize expensive lookups across scans.
6. **Test offline** — use `FakeHttpClient` and `make_module_context` from `tests/modules/fakes.py`.