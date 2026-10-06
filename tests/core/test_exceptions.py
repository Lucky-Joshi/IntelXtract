"""Exception hierarchy tests."""

import pytest

from core.exceptions import (
    ConfigError,
    DatabaseError,
    IntelXtractError,
    MigrationError,
    ModuleError,
    ModuleTimeoutError,
    PluginError,
    PluginLoadError,
    PluginVersionError,
    ScanCancelledError,
    ScanError,
    TaskTimeoutError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc_class",
    [
        ConfigError,
        ValidationError,
        DatabaseError,
        ModuleError,
        PluginError,
        ScanError,
    ],
)
def test_all_derive_from_base(exc_class: type[Exception]) -> None:
    assert issubclass(exc_class, IntelXtractError)
    assert issubclass(exc_class, Exception)


def test_subclass_chains() -> None:
    assert issubclass(MigrationError, DatabaseError)
    assert issubclass(ModuleTimeoutError, ModuleError)
    assert issubclass(PluginLoadError, PluginError)
    assert issubclass(PluginVersionError, PluginError)
    assert issubclass(TaskTimeoutError, ScanError)
    assert issubclass(ScanCancelledError, ScanError)


def test_module_error_carries_module_name() -> None:
    err = ModuleError("boom", module="whois")
    assert err.module == "whois"
    assert str(err) == "boom"


def test_plugin_error_carries_plugin_name() -> None:
    err = PluginLoadError("bad", plugin="VirusTotal")
    assert err.plugin == "VirusTotal"
