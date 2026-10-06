"""Enum and constant contract tests."""

from core.constants import (
    APP_NAME,
    PLUGIN_API_VERSION,
    VERSION,
    ModuleStatus,
    RiskLevel,
    ScanMode,
    ScanStatus,
    Severity,
    TargetType,
    TaskState,
)


def test_version_format() -> None:
    assert VERSION and isinstance(VERSION, str)
    assert APP_NAME == "IntelXtract"
    assert PLUGIN_API_VERSION >= 1


def test_target_types() -> None:
    assert TargetType("domain") is TargetType.DOMAIN
    assert TargetType.UNKNOWN.value == "unknown"
    assert len(TargetType) == 8


def test_severity_and_risk_levels() -> None:
    assert [s.value for s in Severity] == ["info", "low", "medium", "high", "critical"]
    assert [r.value for r in RiskLevel] == ["low", "medium", "high", "critical"]


def test_scan_lifecycle_enums() -> None:
    assert ScanMode("quick") is ScanMode.QUICK
    assert ScanStatus.COMPLETED.value == "completed"
    assert ModuleStatus.TIMEOUT.value == "timeout"
    assert TaskState.PENDING.value == "pending"


def test_str_enum_string_equality() -> None:
    assert TargetType.DOMAIN == "domain"
    assert TaskState.DONE == "done"
