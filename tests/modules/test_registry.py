"""Tests for modules.registry — registration, discovery, and selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.constants import ScanMode, TargetType
from core.engine import ModuleContext
from core.exceptions import ModuleError
from core.models import ModuleResult
from fakes import DummyModule, KeyedDummyModule
from modules.base import BaseModule
from modules.registry import ModuleRegistry


def test_register_lookup_and_names() -> None:
    reg = ModuleRegistry()
    reg.register(DummyModule())
    assert reg.has("dummy")
    assert isinstance(reg.get("dummy"), DummyModule)
    assert reg.get("missing") is None
    assert reg.names() == ["dummy"]
    assert reg.is_enabled("dummy")


def test_register_rejects_duplicate_name() -> None:
    reg = ModuleRegistry()
    reg.register(DummyModule())
    with pytest.raises(ModuleError, match="duplicate"):
        reg.register(DummyModule())
    reg.register(DummyModule(), replace=True)
    assert reg.names() == ["dummy"]


def test_register_rejects_empty_name() -> None:
    reg = ModuleRegistry()

    class Nameless(BaseModule):
        name = ""

        async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
            return ModuleResult()

    with pytest.raises(ModuleError, match="name"):
        reg.register(Nameless())


def test_enable_disable_and_unregister() -> None:
    reg = ModuleRegistry()
    reg.register(DummyModule())
    reg.disable("dummy")
    assert not reg.is_enabled("dummy")
    assert reg.instances() == []
    reg.enable("dummy")
    assert reg.instances() == [reg.get("dummy")]
    reg.unregister("dummy")
    assert not reg.has("dummy")
    with pytest.raises(ModuleError, match="unknown"):
        reg.enable("dummy")


def test_select_respects_enabled_state_and_target_types() -> None:
    reg = ModuleRegistry()
    reg.register(DummyModule())
    reg.register(KeyedDummyModule())
    ip_selection = reg.select(TargetType.IP, ScanMode.QUICK)
    assert ip_selection == ["dummy"]
    reg.disable("dummy")
    assert reg.select(TargetType.DOMAIN, ScanMode.QUICK) == ["dummy_keyed"]
    assert reg.select(TargetType.EMAIL, ScanMode.QUICK) == []
    reg.enable("dummy")
    reg.disable("dummy_keyed")
    assert reg.select(TargetType.DOMAIN, ScanMode.QUICK) == ["dummy"]


def test_infos_reflect_state() -> None:
    reg = ModuleRegistry()
    reg.register(DummyModule())
    reg.disable("dummy")
    info = reg.infos()[0]
    assert info.name == "dummy"
    assert info.cls is DummyModule
    assert info.source == "<explicit>"
    assert info.enabled is False


def _write_package(root: Path, name: str, files: dict[str, str]) -> None:
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for filename, source in files.items():
        (pkg / filename).write_text(source)


def test_discover_registers_module_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_package(
        tmp_path,
        "fixtmods",
        {
            "one.py": (
                "from core.constants import TargetType\n"
                "from modules.base import BaseModule\n"
                "class AlphaModule(BaseModule):\n"
                '    name = "alpha"\n'
                "    target_types = (TargetType.DOMAIN,)\n"
                "    async def run(self, target, ctx):\n"
                "        from core.models import ModuleResult\n"
                "        return ModuleResult(data={'target': target})\n"
            ),
            "two.py": (
                "from modules.base import BaseModule\n"
                "class BetaModule(BaseModule):\n"
                '    name = "beta"\n'
                "    async def run(self, target, ctx):\n"
                "        from core.models import ModuleResult\n"
                "        return ModuleResult()\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = ModuleRegistry()
    infos = reg.discover("fixtmods")

    assert {info.name for info in infos if info.error is None} == {"alpha", "beta"}
    assert reg.has("alpha")
    assert reg.has("beta")
    assert reg.get("alpha").validate("example.com") is True  # type: ignore[union-attr]


def test_discover_reports_name_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = (
        "from modules.base import BaseModule\n"
        "class DupModule(BaseModule):\n"
        '    name = "dup"\n'
        "    async def run(self, target, ctx):\n"
        "        from core.models import ModuleResult\n"
        "        return ModuleResult()\n"
    )
    _write_package(tmp_path, "fixtmods_collide", {"one.py": shared, "two.py": shared})
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = ModuleRegistry()
    infos = reg.discover("fixtmods_collide")

    collisions = [info for info in infos if info.error and "duplicate" in info.error]
    assert len(collisions) == 1
    assert reg.names() == ["dup"]
    assert {info.source for info in collisions} == {"fixtmods_collide.two"}


def test_discover_records_instantiation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_package(
        tmp_path,
        "fixtmods_broken",
        {
            "broken.py": (
                "from modules.base import BaseModule\n"
                "class NeedsArgsModule(BaseModule):\n"
                '    name = "needs_args"\n'
                "    def __init__(self, required):\n"
                "        super().__init__()\n"
                "        self.required = required\n"
                "    async def run(self, target, ctx):\n"
                "        from core.models import ModuleResult\n"
                "        return ModuleResult()\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = ModuleRegistry()
    infos = reg.discover("fixtmods_broken")

    assert [info for info in infos if info.error and "instantiation" in info.error]
    assert not reg.has("needs_args")


def test_discover_ignores_abstract_subclasses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_package(
        tmp_path,
        "fixtmods_abstract",
        {
            "abstract.py": (
                "from abc import abstractmethod\n"
                "from modules.base import BaseModule\n"
                "class AbstractThing(BaseModule):\n"
                '    name = "abstract_thing"\n'
                "    @abstractmethod\n"
                "    def validate(self, target):\n"
                "        ...\n"
                "    async def run(self, target, ctx):\n"
                "        from core.models import ModuleResult\n"
                "        return ModuleResult()\n"
            ),
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    reg = ModuleRegistry()
    infos = reg.discover("fixtmods_abstract")

    assert infos == []
    assert not reg.names()


def test_unknown_package_raises_module_error() -> None:
    reg = ModuleRegistry()
    with pytest.raises(ModuleError, match="cannot import"):
        reg.discover("definitely.not.here")


async def test_registry_provides_engine_ready_instances() -> None:
    reg = ModuleRegistry(packages=())
    assert reg.instances() == []
    reg.register(DummyModule())
    reg.register(KeyedDummyModule())
    assert {m.name for m in reg.instances()} == {"dummy", "dummy_keyed"}
    assert reg.enabled_names() == ["dummy", "dummy_keyed"]
    assert reg.enabled_names(["dummy"]) == ["dummy"]
    reg.disable("dummy")
    assert reg.enabled_names() != [] and "dummy" not in reg.enabled_names()
