"""Plugin discovery and registry.

Plugins are directories under ``plugins/`` containing either ``plugin.py`` or a
``manifest.json`` whose ``entry_point`` names the module to import.  Discovery
is fail-soft: a broken plugin is recorded with an error and never prevents the
application from starting.

The manifest is checked against :data:`MANIFEST_SCHEMA` before import.  Loaded
plugins can be surfaced as engine modules through :class:`PluginModuleAdapter`
so they run through the exact same scan pipeline as core collectors.
"""

from __future__ import annotations

import importlib.util
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from core.constants import PLUGIN_API_VERSION, TargetType
from core.exceptions import PluginLoadError, PluginVersionError
from core.models import ModuleResult, parse_findings

PLUGIN_FILE = "plugin.py"
MANIFEST_FILE = "manifest.json"

MANIFEST_SCHEMA: dict[str, dict[str, Any]] = {
    "name": {"type": "string", "required": False},
    "version": {"type": "string", "required": False},
    "api_version": {"type": "integer", "required": False, "min": 1},
    "author": {"type": "string", "required": False},
    "description": {"type": "string", "required": False},
    "entry_point": {"type": "string", "required": False},
    "target_types": {"type": "array", "items": "target_type", "required": False},
    "required_keys": {"type": "array", "items": "string", "required": False},
}


class PluginBase(ABC):
    """Interface every IntelXtract plugin implements."""

    name: str = ""
    version: str = "0.1.0"
    api_version: int = PLUGIN_API_VERSION
    author: str = ""
    description: str = ""
    target_types: tuple[TargetType, ...] = ()
    requires_keys: tuple[str, ...] = ()

    def validate(self, target: str) -> bool:
        """Return whether this plugin can run against ``target``."""
        return bool(target and target.strip())

    @abstractmethod
    async def run(self, target: str, ctx: Any) -> Any:
        """Execute the plugin against ``target`` and return its result."""
        raise NotImplementedError


@dataclass(slots=True)
class PluginInfo:
    """Discovered plugin metadata (also used for reporting load errors)."""

    name: str
    version: str
    api_version: int
    source: Path
    author: str = ""
    description: str = ""
    target_types: tuple[TargetType, ...] = ()
    requires_keys: tuple[str, ...] = ()
    error: str | None = None
    instance: PluginBase | None = field(default=None, repr=False, compare=False)


def validate_manifest(data: Mapping[str, Any]) -> list[str]:
    """Return schema violations for a manifest mapping (empty when valid).

    Manifest fields are overrides: the plugin class is the source of truth for
    anything omitted, so every field is optional.  Known fields are
    type/format checked; unknown keys are tolerated for forward compatibility.
    """
    errors: list[str] = []
    for field_name, spec in MANIFEST_SCHEMA.items():
        present = field_name in data and data[field_name] is not None
        if not present:
            if spec.get("required"):
                errors.append(f"{field_name}: required field is missing")
            continue
        value = data[field_name]
        kind = spec["type"]
        if kind == "string":
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{field_name}: must be a non-empty string")
            elif field_name == "entry_point" and (
                Path(value).is_absolute() or ".." in Path(value).parts
            ):
                errors.append(
                    f"{field_name}: must be a relative path inside the plugin"
                )
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{field_name}: must be an integer")
            elif value < spec.get("min", value):
                errors.append(f"{field_name}: must be >= {spec['min']}")
        elif kind == "array":
            if not isinstance(value, list):
                errors.append(f"{field_name}: must be a list")
                continue
            item_kind = spec["items"]
            for index, item in enumerate(value):
                if not isinstance(item, str):
                    errors.append(f"{field_name}[{index}]: must be a string")
                elif item_kind == "target_type" and item not in {
                    t.value for t in TargetType
                }:
                    errors.append(
                        f"{field_name}[{index}]: unknown target type {item!r}"
                    )
    return errors


def _load_module(source: Path, package: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(package, source)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"cannot create import spec for {source}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginLoadError(f"import failed: {exc}") from exc
    return module


def _find_plugin_class(module: ModuleType) -> type[PluginBase] | None:
    for attr_name in dir(module):
        candidate = getattr(module, attr_name)
        if (
            isinstance(candidate, type)
            and issubclass(candidate, PluginBase)
            and candidate is not PluginBase
        ):
            return candidate
    return None


def _read_manifest(directory: Path) -> dict[str, Any]:
    manifest_path = directory / MANIFEST_FILE
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginLoadError(f"invalid {MANIFEST_FILE}: {exc}") from exc
    if not isinstance(data, dict):
        raise PluginLoadError(f"{MANIFEST_FILE} must contain a JSON object")
    return data


def _resolve_entry(directory: Path, manifest: Mapping[str, Any]) -> Path:
    entry = str(manifest.get("entry_point") or PLUGIN_FILE)
    source = (directory / entry).resolve()
    try:
        source.relative_to(directory.resolve())
    except ValueError as exc:
        raise PluginLoadError(f"entry_point escapes plugin directory: {entry}") from exc
    if not source.is_file():
        raise PluginLoadError(f"entry_point not found: {entry}")
    return source


def _coerce_target_types(
    manifest: Mapping[str, Any], instance: PluginBase
) -> tuple[TargetType, ...]:
    if "target_types" in manifest:
        return tuple(TargetType(value) for value in manifest["target_types"])
    return tuple(instance.target_types)


def _coerce_required_keys(
    manifest: Mapping[str, Any], instance: PluginBase
) -> tuple[str, ...]:
    if "required_keys" in manifest:
        return tuple(str(key) for key in manifest["required_keys"])
    return tuple(instance.requires_keys)


class PluginRegistry:
    """Discovers plugins from a directory and tracks enable/disable state."""

    def __init__(self, plugins_dir: Path | str) -> None:
        self._dir = Path(plugins_dir)
        self._plugins: dict[str, PluginInfo] = {}
        self._disabled: set[str] = set()

    @property
    def directory(self) -> Path:
        """Directory scanned for plugins."""
        return self._dir

    def discover(self) -> list[PluginInfo]:
        """Scan the plugin directory; returns every entry (errors included)."""
        self._plugins.clear()
        if not self._dir.is_dir():
            return []
        for child in sorted(self._dir.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            has_manifest = (child / MANIFEST_FILE).is_file()
            has_source = (child / PLUGIN_FILE).is_file()
            if not (has_manifest or has_source):
                continue
            info = self._load_one(child)
            self._plugins[info.name] = info
        return list(self._plugins.values())

    def _load_one(self, directory: Path) -> PluginInfo:
        base = PluginInfo(
            name=directory.name,
            version="0.0.0",
            api_version=PLUGIN_API_VERSION,
            source=directory / PLUGIN_FILE,
        )
        try:
            manifest = _read_manifest(directory)
            violations = validate_manifest(manifest)
            if violations:
                raise PluginLoadError(
                    "invalid manifest: " + "; ".join(violations),
                    plugin=directory.name,
                )
            declared_api = int(manifest.get("api_version", PLUGIN_API_VERSION))
            if declared_api > PLUGIN_API_VERSION:
                raise PluginVersionError(
                    f"plugin requires api_version {declared_api}, "
                    f"supported: {PLUGIN_API_VERSION}",
                    plugin=directory.name,
                )
            source = _resolve_entry(directory, manifest)
            base.source = source
            module = _load_module(source, f"intelxtract_plugins.{directory.name}")
            cls = _find_plugin_class(module)
            if cls is None:
                raise PluginLoadError(
                    f"no PluginBase subclass found in {source.name}",
                    plugin=directory.name,
                )
            instance = cls()
            if not instance.name:
                instance.name = directory.name
            base.name = str(manifest.get("name") or instance.name)
            base.version = str(manifest.get("version", instance.version))
            base.api_version = declared_api
            base.author = str(manifest.get("author", instance.author))
            base.description = str(manifest.get("description", instance.description))
            base.target_types = _coerce_target_types(manifest, instance)
            base.requires_keys = _coerce_required_keys(manifest, instance)
            base.instance = instance
        except (PluginLoadError, PluginVersionError, TypeError, ValueError) as exc:
            base.error = str(exc)
        return base

    def get(self, name: str) -> PluginInfo | None:
        """Return metadata for a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """All discovered plugins in discovery order."""
        return list(self._plugins.values())

    def runnable(self) -> list[PluginBase]:
        """Instances that loaded cleanly and are enabled."""
        instances: list[PluginBase] = []
        for info in self._plugins.values():
            if (
                info.error is None
                and info.instance is not None
                and info.name not in self._disabled
            ):
                instances.append(info.instance)
        return instances

    def engine_modules(self) -> list[PluginModuleAdapter]:
        """Enabled, cleanly-loaded plugins adapted for the scan engine."""
        modules: list[PluginModuleAdapter] = []
        for info in self._plugins.values():
            if info.error is not None or info.instance is None:
                continue
            if info.name in self._disabled:
                continue
            modules.append(PluginModuleAdapter(info))
        return modules

    def apply_state(self, states: Mapping[str, bool]) -> None:
        """Apply persisted enable/disable flags for known plugins."""
        for name, enabled in states.items():
            if name not in self._plugins:
                continue
            if enabled:
                self._disabled.discard(name)
            else:
                self._disabled.add(name)

    def enable(self, name: str) -> None:
        """Enable a plugin (raises :class:`PluginLoadError` when unknown)."""
        self._require(name)
        self._disabled.discard(name)

    def disable(self, name: str) -> None:
        """Disable a plugin without removing it."""
        self._require(name)
        self._disabled.add(name)

    def is_enabled(self, name: str) -> bool:
        """Whether the plugin exists and is enabled."""
        return name in self._plugins and name not in self._disabled

    def _require(self, name: str) -> None:
        if name not in self._plugins:
            raise PluginLoadError(f"unknown plugin: {name}", plugin=name)


class PluginModuleAdapter:
    """Expose a loaded plugin as a scan module for the engine pipeline.

    The adapter mirrors the module contract (``name``/``target_types``/
    ``requires_keys``/``validate``/``run``) and normalizes whatever the plugin
    returns into a :class:`core.models.ModuleResult`, so plugins and core
    collectors are consumed identically by :class:`core.engine.ScanEngine`.
    """

    def __init__(self, info: PluginInfo) -> None:
        if info.error is not None or info.instance is None:
            raise PluginLoadError(
                f"plugin {info.name!r} is not runnable ({info.error or 'no instance'})",
                plugin=info.name,
            )
        self._plugin = info.instance
        self.name = info.name
        self.version = info.version
        self.description = info.description
        self.target_types = info.target_types
        self.requires_keys = info.requires_keys

    def validate(self, target: str) -> bool:
        """Delegate target validation to the wrapped plugin."""
        return self._plugin.validate(target)

    async def run(self, target: str, ctx: Any) -> ModuleResult:
        """Run the plugin and normalize its output to a ``ModuleResult``."""
        result = await self._plugin.run(target, ctx)
        if isinstance(result, ModuleResult):
            return result
        data = dict(result) if isinstance(result, Mapping) else {"result": result}
        return ModuleResult(
            data=data,
            findings=tuple(parse_findings(self.name, result)),
        )


__all__ = [
    "MANIFEST_FILE",
    "MANIFEST_SCHEMA",
    "PLUGIN_FILE",
    "PluginBase",
    "PluginInfo",
    "PluginModuleAdapter",
    "PluginRegistry",
    "validate_manifest",
]
