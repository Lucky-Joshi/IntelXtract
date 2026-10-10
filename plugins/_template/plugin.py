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
