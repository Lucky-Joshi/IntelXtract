# IntelXtract Plugin SDK

Plugins are self-contained collectors that run through the same scan pipeline
as the built-in modules. Drop a directory under `plugins/`, and IntelXtract
discovers, validates, loads, and (when enabled and applicable) runs it.

The reference implementations live in [`plugins/Wayback/`](../plugins/Wayback) and
[`plugins/VirusTotal/`](../plugins/VirusTotal). A copy-me skeleton is in
[`plugins/_template/`](../plugins/_template).

## Layout

```
plugins/
  YourPlugin/
    manifest.json   # required for discovery + validation
    plugin.py       # entry point (configurable via manifest.entry_point)
    requirements    # optional free-form notes/deps for your own reference
```

Discovery is **fail-soft**: a plugin that fails manifest validation, import, or
class lookup is recorded with an error and simply skipped — it never prevents
the application from starting or other plugins from running.

## `manifest.json`

Validated against the SDK schema (`core.plugin_loader.MANIFEST_SCHEMA`).

| Field           | Type            | Required | Notes                                                              |
|-----------------|-----------------|----------|--------------------------------------------------------------------|
| `name`          | string          | yes      | Registry name; must be non-empty. Defaults to the directory name.   |
| `version`       | string          | yes      | Plugin version (e.g. `1.0.0`).                                     |
| `api_version`   | integer ≥ 1     | no       | SDK version the plugin targets. Must be ≤ `PLUGIN_API_VERSION` (1). |
| `author`        | string          | no       | Author/owner.                                                      |
| `description`   | string          | no       | One-line summary shown by `intelxtract plugin info`.              |
| `entry_point`   | relative string | no       | Module to import (default `plugin.py`); must stay inside the dir.  |
| `target_types`  | string[]        | no       | Target kinds it applies to (`domain`, `ip`, `url`, `email`, `username`, `hash`, `file`, `unknown`). |
| `required_keys` | string[]        | no       | `api_keys.*` names that must be configured before it runs.         |

Unknown keys are tolerated for forward compatibility. Invalid known fields
make the manifest invalid and the plugin is reported with the reason.

`api_version` is a compatibility gate: a plugin declaring a newer SDK than the
running application refuses to load (recorded, not fatal).

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

- You may declare metadata in the class, in `manifest.json`, or both;
  manifest values win when present.
- Return a `ModuleResult`. Anything else is normalized for you: mappings become
  `data`, and any `findings`/`records`/`title`-shaped content is parsed into
  `Finding` objects (see `core.models.parse_findings`).
- Prefer `make_finding(...)` so findings get a stable `content_hash` for
  deduplication.

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

### Failure behavior

- Raise, or return a finding with `Severity.INFO` — either way the engine
  records a per-module status; a raised exception fails only that module's run,
  never the scan. Example plugins catch network errors and report an
  "unavailable" finding rather than raising.

## CLI

```bash
intelxtract plugin list                 # discovered plugins + errors + enabled state
intelxtract plugin info wayback         # manifest details, source, target types
intelxtract plugin enable virustotal    # persisted in the database
intelxtract plugin disable wayback
```

Enable/disable state is persisted in the `plugins` table; use
`PluginRegistry.apply_state(...)` to hydrate it at load time.

## Running through the engine

`PluginRegistry.engine_modules()` returns `PluginModuleAdapter` instances that
satisfy the engine's module contract, so plugins and core collectors are
indistinguishable to `ScanEngine`:

```python
registry = PluginRegistry(plugins_dir)
registry.discover()
registry.apply_state({"wayback": True, "virustotal": False})
engine = ScanEngine(config, modules=registry.engine_modules())
result = await engine.scan("example.com", mode="deep")
```

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

## Versioning

Bump `api_version` only when the plugin relies on a newer SDK. The current SDK
version is `core.constants.PLUGIN_API_VERSION` (currently `1`).
