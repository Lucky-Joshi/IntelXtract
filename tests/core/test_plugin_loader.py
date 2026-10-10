"""Plugin discovery and registry tests."""

import json
from pathlib import Path

import pytest

from core.constants import TargetType
from core.exceptions import PluginLoadError
from core.models import ModuleResult
from core.plugin_loader import (
    PluginModuleAdapter,
    PluginRegistry,
    validate_manifest,
)
from fakes import FakeHttpClient, make_module_config, make_module_context

VALID_PLUGIN = """
from core.constants import TargetType
from core.plugin_loader import PluginBase


class DemoPlugin(PluginBase):
    name = "demo"
    version = "1.2.3"
    description = "demo plugin"
    target_types = (TargetType.DOMAIN,)

    async def run(self, target, ctx):
        return {"echo": target}
"""

SIMPLE_PLUGIN = """
from core.plugin_loader import PluginBase


class Simple(PluginBase):
    name = "simple"

    async def run(self, target, ctx):
        return target
"""

BROKEN_PLUGIN = """
raise RuntimeError("plugin explodes on import")
"""

NO_CLASS_PLUGIN = """
x = 42
"""


def _write_plugin(
    root: Path, name: str, source: str, manifest: dict | None = None
) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "plugin.py").write_text(source, encoding="utf-8")
    if manifest is not None:
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


async def test_discover_valid_plugin(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo", VALID_PLUGIN)
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert len(infos) == 1
    info = infos[0]
    assert info.name == "demo"
    assert info.version == "1.2.3"
    assert info.description == "demo plugin"
    assert info.target_types == (TargetType.DOMAIN,)
    assert info.error is None
    assert info.instance is not None

    runnable = registry.runnable()
    assert len(runnable) == 1
    result = await runnable[0].run("example.com", None)
    assert result == {"echo": "example.com"}


async def test_manifest_overrides_version(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path,
        "simple",
        SIMPLE_PLUGIN,
        {"version": "9.9.9", "description": "from manifest"},
    )
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].version == "9.9.9"
    assert infos[0].description == "from manifest"
    assert infos[0].error is None


def test_manifest_future_api_version_is_fail_soft(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "future", SIMPLE_PLUGIN, {"api_version": 999})
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].error is not None
    assert "api_version" in infos[0].error
    assert registry.runnable() == []


def test_import_error_is_fail_soft(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "broken", BROKEN_PLUGIN)
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert len(infos) == 1
    assert infos[0].error is not None
    assert "explodes" in infos[0].error
    assert registry.runnable() == []


def test_missing_plugin_class_is_fail_soft(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "noclass", NO_CLASS_PLUGIN)
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].error is not None
    assert "PluginBase subclass" in infos[0].error


def test_ignores_non_plugin_dirs_and_files(tmp_path: Path) -> None:
    (tmp_path / "_template").mkdir()
    (tmp_path / "_template" / "plugin.py").write_text("x=1", encoding="utf-8")
    (tmp_path / "empty_dir").mkdir()
    (tmp_path / "stray.py").write_text("x=1", encoding="utf-8")
    _write_plugin(tmp_path, "real", SIMPLE_PLUGIN)
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert [i.name for i in infos] == ["simple"]


def test_missing_directory_is_empty(tmp_path: Path) -> None:
    registry = PluginRegistry(tmp_path / "nope")
    assert registry.discover() == []


def test_enable_disable(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "simple", SIMPLE_PLUGIN)
    registry = PluginRegistry(tmp_path)
    registry.discover()
    assert registry.is_enabled("simple")
    assert len(registry.runnable()) == 1

    registry.disable("simple")
    assert not registry.is_enabled("simple")
    assert registry.runnable() == []

    registry.enable("simple")
    assert registry.is_enabled("simple")
    assert len(registry.runnable()) == 1

    with pytest.raises(PluginLoadError):
        registry.disable("ghost")


def test_default_name_falls_back_to_directory(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path,
        "dirname",
        """
from core.plugin_loader import PluginBase


class Anon(PluginBase):
    async def run(self, target, ctx):
        return target
""",
    )
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].name == "dirname"
    assert infos[0].error is None


# --- S20.1 manifest schema ---------------------------------------------------


def test_validate_manifest_accepts_minimal_and_extra() -> None:
    assert validate_manifest({}) == []
    assert (
        validate_manifest(
            {
                "name": "demo",
                "version": "1.0.0",
                "api_version": 1,
                "author": "me",
                "entry_point": "plugin.py",
                "target_types": ["domain", "ip"],
                "required_keys": ["demo"],
                "unexpected": "forward-compatible",
            }
        )
        == []
    )


def test_validate_manifest_rejects_bad_types() -> None:
    errors = validate_manifest(
        {
            "name": 5,
            "version": "",
            "api_version": "1",
            "target_types": ["domain", "nope"],
            "required_keys": "virustotal",
            "entry_point": "../escape.py",
        }
    )
    assert any("name" in error for error in errors)
    assert any("version" in error for error in errors)
    assert any("api_version" in error for error in errors)
    assert any("target_types[1]" in error for error in errors)
    assert any("required_keys" in error for error in errors)
    assert any("entry_point" in error for error in errors)


def test_invalid_manifest_is_fail_soft(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo", SIMPLE_PLUGIN, {"version": 3})  # wrong type
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].error is not None
    assert "invalid manifest" in infos[0].error
    assert registry.runnable() == []


def test_entry_point_selects_module(tmp_path: Path) -> None:
    directory = tmp_path / "custom"
    directory.mkdir()
    (directory / "collector.py").write_text(SIMPLE_PLUGIN, encoding="utf-8")
    (directory / "manifest.json").write_text(
        json.dumps(
            {"name": "custom", "version": "2.0.0", "entry_point": "collector.py"}
        ),
        encoding="utf-8",
    )
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].error is None
    assert infos[0].name == "custom"
    assert infos[0].source.name == "collector.py"


def test_missing_entry_point_is_fail_soft(tmp_path: Path) -> None:
    directory = tmp_path / "custom"
    directory.mkdir()
    (directory / "manifest.json").write_text(
        json.dumps({"name": "custom", "version": "1.0.0", "entry_point": "nope.py"}),
        encoding="utf-8",
    )
    registry = PluginRegistry(tmp_path)
    infos = registry.discover()
    assert infos[0].error is not None
    assert "entry_point" in infos[0].error


def test_manifest_supplies_target_types_and_keys(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path,
        "demo",
        SIMPLE_PLUGIN,
        {
            "name": "demo",
            "version": "1.0.0",
            "target_types": ["ip"],
            "required_keys": ["demo"],
            "author": "ops",
        },
    )
    registry = PluginRegistry(tmp_path)
    info = registry.discover()[0]
    assert info.target_types == (TargetType.IP,)
    assert info.requires_keys == ("demo",)
    assert info.author == "ops"


def test_apply_state_hydrates_enable_disable(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "simple", SIMPLE_PLUGIN)
    registry = PluginRegistry(tmp_path)
    registry.discover()
    registry.apply_state({"simple": False, "ghost": True})
    assert not registry.is_enabled("simple")
    assert registry.runnable() == []
    registry.apply_state({"simple": True})
    assert registry.is_enabled("simple")


# --- S20.2 engine adapter ----------------------------------------------------


async def test_engine_modules_returns_adapters(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "demo", VALID_PLUGIN)
    registry = PluginRegistry(tmp_path)
    registry.discover()
    modules = registry.engine_modules()
    assert len(modules) == 1
    adapter = modules[0]
    assert adapter.name == "demo"
    assert adapter.version == "1.2.3"
    assert adapter.target_types == (TargetType.DOMAIN,)
    assert adapter.validate("example.com")
    result = await adapter.run("example.com", None)
    assert isinstance(result, ModuleResult)
    assert result.data == {"echo": "example.com"}


async def test_adapter_normalizes_mapping_result(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path,
        "listing",
        """
from core.plugin_loader import PluginBase


class Listing(PluginBase):
    name = "listing"

    async def run(self, target, ctx):
        return {"findings": [{"title": "found", "severity": "low"}]}
""",
    )
    registry = PluginRegistry(tmp_path)
    registry.discover()
    adapter = registry.engine_modules()[0]
    result = await adapter.run("target", None)
    assert isinstance(result, ModuleResult)
    assert [finding.title for finding in result.findings] == ["found"]


def test_engine_modules_skips_broken_and_disabled(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "simple", SIMPLE_PLUGIN)
    _write_plugin(tmp_path, "broken", BROKEN_PLUGIN)
    registry = PluginRegistry(tmp_path)
    registry.discover()
    names = [module.name for module in registry.engine_modules()]
    assert names == ["simple"]
    registry.disable("simple")
    assert registry.engine_modules() == []


def test_adapter_rejects_unrunnable_info(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "broken", BROKEN_PLUGIN)
    registry = PluginRegistry(tmp_path)
    info = registry.discover()[0]
    with pytest.raises(PluginLoadError):
        PluginModuleAdapter(info)


async def test_adapter_uses_context(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path,
        "http_probe",
        """
from core.constants import TargetType
from core.plugin_loader import PluginBase


class Probe(PluginBase):
    name = "http_probe"
    target_types = (TargetType.DOMAIN,)

    async def run(self, target, ctx):
        key = ctx.api_key("demo")
        return {"key": key, "target": target}
""",
    )
    registry = PluginRegistry(tmp_path)
    registry.discover()
    adapter = registry.engine_modules()[0]
    config = make_module_config(tmp_path, key="demo", secret="s3cret")
    ctx = make_module_context(config, http=FakeHttpClient())
    result = await adapter.run("example.com", ctx)
    assert result.data["key"] == "s3cret"
