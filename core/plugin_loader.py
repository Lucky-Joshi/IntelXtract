"""Plugin discovery and registry.

Plugins are directories under ``plugins/`` containing ``plugin.py`` (and an
optional ``manifest.json``).  Discovery is fail-soft: a broken plugin is
recorded with an error and never prevents the application from starting.
"""

from __future__ import annotations

import importlib.util
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from core.constants import PLUGIN_API_VERSION, TargetType
from core.exceptions import PluginLoadError, PluginVersionError

PLUGIN_FILE = "plugin.py"
MANIFEST_FILE = "manifest.json"


class PluginBase(ABC):
    """Interface every IntelXtract plugin implements."""

    name: str = ""
    version: str = "0.1.0"
    api_version: int = PLUGIN_API_VERSION
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
    description: str = ""
    target_types: tuple[TargetType, ...] = ()
    error: str | None = None
    instance: PluginBase | None = field(default=None, repr=False, compare=False)


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
            source = child / PLUGIN_FILE
            if not source.is_file():
                continue
            self._plugins[child.name] = self._load_one(child, source)
        return list(self._plugins.values())

    def _load_one(self, directory: Path, source: Path) -> PluginInfo:
        base = PluginInfo(
            name=directory.name,
            version="0.0.0",
            api_version=PLUGIN_API_VERSION,
            source=source,
        )
        try:
            manifest = _read_manifest(directory)
            declared_api = int(manifest.get("api_version", PLUGIN_API_VERSION))
            if declared_api > PLUGIN_API_VERSION:
                raise PluginVersionError(
                    f"plugin requires api_version {declared_api}, "
                    f"supported: {PLUGIN_API_VERSION}",
                    plugin=directory.name,
                )
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
            base.name = instance.name
            base.version = str(manifest.get("version", instance.version))
            base.api_version = declared_api
            base.description = str(manifest.get("description", instance.description))
            base.target_types = tuple(instance.target_types)
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
