"""Module discovery and lifecycle registry (Phase 7).

The :class:`ModuleRegistry` collects :class:`BaseModule` implementations —
from explicit :meth:`ModuleRegistry.register` calls or by importing packages
(conventionally top-level packages under ``modules/``) — guards against name
collisions, and tracks per-name enable/disable state.  The engine can then be
built from :meth:`ModuleRegistry.instances` for a curated, profile-aware
module set.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from core.constants import ScanMode, TargetType
from core.exceptions import ModuleError
from core.input_engine import select_modules
from modules.base import BaseModule

EXPLICIT_SOURCE = "<explicit>"


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    """Registry metadata for one discovered module."""

    name: str
    cls: type[BaseModule] | None
    source: str
    enabled: bool
    error: str | None = None


def _module_classes(namespace: object) -> list[type[BaseModule]]:
    """Concrete ``BaseModule`` subclasses exposed by an imported module."""
    return [
        obj
        for _, obj in inspect.getmembers(
            namespace,
            lambda member: isinstance(member, type) and issubclass(member, BaseModule),
        )
        if obj is not BaseModule and not getattr(obj, "__abstractmethods__", ())
    ]


class ModuleRegistry:
    """Collects, orders, and toggles the project's scan modules."""

    def __init__(self, *, packages: Sequence[str] = ()) -> None:
        self._modules: dict[str, BaseModule] = {}
        self._sources: dict[str, str] = {}
        self._disabled: set[str] = set()
        for package in packages:
            self.discover(package)

    def register(
        self,
        module: BaseModule,
        *,
        replace: bool = False,
        source: str = EXPLICIT_SOURCE,
    ) -> None:
        """Register a module instance; duplicate names raise :class:`ModuleError`."""
        name = module.name
        if not name or not str(name).strip():
            raise ModuleError("module must declare a non-empty name")
        if name in self._modules and not replace:
            raise ModuleError(
                f"duplicate module {name!r} (already provided by "
                f"{self._sources.get(name, EXPLICIT_SOURCE)})"
            )
        self._modules[name] = module
        self._sources[name] = source
        self._disabled.discard(name)

    def unregister(self, name: str) -> None:
        """Remove a module and its enable/disable state."""
        if name not in self._modules:
            raise ModuleError(f"unknown module {name!r}")
        del self._modules[name]
        del self._sources[name]
        self._disabled.discard(name)

    def discover(self, package: str) -> list[ModuleInfo]:
        """Import ``package`` (and submodules) and register its modules.

        Individual import/instantiation failures are reported per-entry on the
        returned :class:`ModuleInfo` objects rather than aborting discovery.
        """
        try:
            root = importlib.import_module(package)
        except ModuleNotFoundError as exc:
            raise ModuleError(
                f"cannot import module package {package!r}: {exc}"
            ) from exc
        infos: list[ModuleInfo] = []
        for mod_info in pkgutil.walk_packages(root.__path__, prefix=f"{package}."):
            try:
                namespace = importlib.import_module(mod_info.name)
            except Exception as exc:
                infos.append(
                    ModuleInfo(
                        name=f"{mod_info.name} (import error)",
                        cls=None,
                        source=mod_info.name,
                        enabled=False,
                        error=str(exc),
                    )
                )
                continue
            for cls in _module_classes(namespace):
                self._register_class(cls, mod_info.name, infos)
        return infos

    def _register_class(
        self,
        cls: type[BaseModule],
        source: str,
        infos: list[ModuleInfo],
    ) -> None:
        try:
            instance = cls()
        except Exception as exc:
            infos.append(
                ModuleInfo(
                    name=getattr(cls, "name", "") or cls.__qualname__,
                    cls=cls,
                    source=source,
                    enabled=False,
                    error=f"instantiation failed: {exc}",
                )
            )
            return
        name = instance.name
        if not name or not str(name).strip():
            infos.append(
                ModuleInfo(
                    name=cls.__qualname__,
                    cls=cls,
                    source=source,
                    enabled=False,
                    error="module must declare a non-empty name",
                )
            )
            return
        if name in self._modules:
            infos.append(
                ModuleInfo(
                    name=name,
                    cls=cls,
                    source=source,
                    enabled=self.is_enabled(name),
                    error=(
                        f"duplicate module name, already provided by "
                        f"{self._sources.get(name, EXPLICIT_SOURCE)}"
                    ),
                )
            )
            return
        self._modules[name] = instance
        self._sources[name] = source
        infos.append(ModuleInfo(name=name, cls=cls, source=source, enabled=True))

    def get(self, name: str) -> BaseModule | None:
        """Return the registered instance, or ``None`` when unknown."""
        return self._modules.get(name)

    def has(self, name: str) -> bool:
        """True when ``name`` is registered."""
        return name in self._modules

    def names(self) -> list[str]:
        """Registered names in sorted order."""
        return sorted(self._modules)

    def enable(self, name: str) -> None:
        """Mark a module as enabled (unknown names raise)."""
        if name not in self._modules:
            raise ModuleError(f"unknown module {name!r}")
        self._disabled.discard(name)

    def disable(self, name: str) -> None:
        """Mark a module as disabled so the engine never plans it."""
        if name not in self._modules:
            raise ModuleError(f"unknown module {name!r}")
        self._disabled.add(name)

    def is_enabled(self, name: str) -> bool:
        """True when the module is registered and not disabled."""
        return name in self._modules and name not in self._disabled

    def instances(self) -> list[BaseModule]:
        """Enabled module instances in sorted name order (engine-ready)."""
        return [
            self._modules[name] for name in self.names() if name not in self._disabled
        ]

    def infos(self) -> list[ModuleInfo]:
        """Current metadata for every registered module, sorted by name."""
        return [
            ModuleInfo(
                name=name,
                cls=type(module),
                source=self._sources.get(name, EXPLICIT_SOURCE),
                enabled=name not in self._disabled,
            )
            for name, module in sorted(self._modules.items())
        ]

    def select(self, target_type: TargetType, mode: ScanMode) -> list[str]:
        """Enabled names applicable to ``target_type`` under ``mode``.

        Uses the Phase 6 selection map when it lists any registered module,
        otherwise falls back to every registered name.
        """
        if not self._modules:
            return []
        available = frozenset(self._modules)
        selected = select_modules(target_type, mode, available=available)
        if not selected:
            selected = sorted(available)
        return sorted(
            name
            for name in selected
            if self.is_enabled(name) and self._applies(name, target_type)
        )

    def _applies(self, name: str, target_type: TargetType) -> bool:
        module = self._modules[name]
        if not module.target_types:
            return True
        return target_type in module.target_types

    def enabled_names(self, names: Iterable[str] | None = None) -> list[str]:
        """Subset of ``names`` (or all registered) that are enabled, sorted."""
        subset = set(names) if names is not None else set(self._modules)
        return sorted(name for name in subset if self.is_enabled(name))
