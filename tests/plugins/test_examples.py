"""Phase 20 example-plugin tests (S20.3/S20.5).

Loads the bundled ``plugins/Wayback`` and ``plugins/VirusTotal`` references,
runs them offline through the shared ``ModuleContext`` doubles, and proves the
engine pipeline consumes a plugin adapter exactly like a core module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.constants import Severity
from core.engine import ScanEngine
from core.plugin_loader import PluginBase, PluginRegistry
from fakes import FakeHttpClient, make_module_config, make_module_context

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_DIR = REPO_ROOT / "plugins"

CDX_URL = "https://web.archive.org/cdx/search/cdx"
VT_URL = "https://www.virustotal.com/api/v3/domains/example.com"


def _load_plugin(name: str) -> PluginBase:
    registry = PluginRegistry(PLUGINS_DIR)
    registry.discover()
    info = registry.get(name)
    assert info is not None and info.instance is not None
    return info.instance


@pytest.fixture
def registry() -> PluginRegistry:
    registry = PluginRegistry(PLUGINS_DIR)
    registry.discover()
    return registry


def test_bundled_plugins_discover_cleanly(registry: PluginRegistry) -> None:
    names = {info.name for info in registry.list_plugins()}
    assert {"wayback", "virustotal"} <= names
    for name in ("wayback", "virustotal"):
        info = registry.get(name)
        assert info is not None
        assert info.error is None
        assert info.author == "IntelXtract"
        assert info.version == "1.0.0"


def test_virustotal_declares_required_key(registry: PluginRegistry) -> None:
    info = registry.get("virustotal")
    assert info is not None
    assert info.requires_keys == ("virustotal",)


async def test_wayback_reports_captures(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        CDX_URL,
        body=[
            ["timestamp", "original", "statuscode"],
            ["20140101000000", "http://example.com/", "200"],
            ["20240101000000", "https://example.com/", "200"],
        ],
    )
    plugin = _load_plugin("wayback")
    ctx = make_module_context(make_module_config(tmp_path), http=client)
    result = await plugin.run("example.com", ctx)
    titles = [finding.title for finding in result.findings]
    assert titles == ["Wayback: 2 archived capture(s)"]
    assert result.data["count"] == 2
    assert result.findings[0].data["oldest"] == "20140101000000"


async def test_wayback_handles_empty_archive(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(CDX_URL, body=[])
    plugin = _load_plugin("wayback")
    ctx = make_module_context(make_module_config(tmp_path), http=client)
    result = await plugin.run("example.com", ctx)
    assert result.findings[0].title == "Wayback: no archived captures"


async def test_wayback_reports_unavailable_on_failure(tmp_path: Path) -> None:
    client = FakeHttpClient()  # unstubbed -> 404 -> HttpError
    plugin = _load_plugin("wayback")
    ctx = make_module_context(make_module_config(tmp_path), http=client)
    result = await plugin.run("example.com", ctx)
    assert result.findings[0].title == "Wayback: archive lookup unavailable"
    assert result.findings[0].severity is Severity.INFO


async def test_virustotal_without_key_is_informational(tmp_path: Path) -> None:
    plugin = _load_plugin("virustotal")
    ctx = make_module_context(make_module_config(tmp_path), http=FakeHttpClient())
    result = await plugin.run("example.com", ctx)
    assert result.findings[0].title == "VirusTotal: not configured"


async def test_virustotal_reports_detections(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        VT_URL,
        body={
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 6,
                        "suspicious": 1,
                        "harmless": 60,
                        "undetected": 3,
                    }
                }
            }
        },
    )
    config = make_module_config(tmp_path, key="virustotal", secret="test-key")
    plugin = _load_plugin("virustotal")
    ctx = make_module_context(config, http=client)
    result = await plugin.run("example.com", ctx)
    finding = result.findings[0]
    assert finding.severity is Severity.CRITICAL
    assert finding.data["malicious"] == 6
    assert result.data["total_engines"] == 70
    # api key travels in the request headers, never hardcoded
    assert client.requests[0]["kwargs"]["headers"] == {"x-apikey": "test-key"}


async def test_plugin_runs_through_engine_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeHttpClient()
    client.stub(
        CDX_URL,
        body=[
            ["timestamp", "original", "statuscode"],
            ["20150101000000", "http://example.com/", "200"],
        ],
    )
    monkeypatch.setattr("core.engine.HttpClient", lambda config=None, **kwargs: client)

    registry = PluginRegistry(PLUGINS_DIR)
    registry.discover()
    engine = ScanEngine(make_module_config(tmp_path), modules=registry.engine_modules())
    result = await engine.scan("example.com", mode="deep", module_names=["wayback"])

    run = next(r for r in result.runs if r.module == "wayback")
    assert run.status.value == "success"
    assert any(
        finding["module"] == "wayback"
        and finding["title"].startswith("Wayback: 1 archived")
        for finding in result.findings
    )
    assert client.aclosed
