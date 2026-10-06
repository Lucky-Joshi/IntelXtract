"""Shared enumerations and application-wide constants."""

from enum import StrEnum

VERSION = "0.1.0a0"
APP_NAME = "IntelXtract"
PLUGIN_API_VERSION = 1


class TargetType(StrEnum):
    """Classified target kinds recognized by the input engine."""

    DOMAIN = "domain"
    IP = "ip"
    URL = "url"
    EMAIL = "email"
    USERNAME = "username"
    HASH = "hash"
    FILE = "file"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Finding severity levels (emitted by modules)."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(StrEnum):
    """Aggregate risk bands produced by the risk engine."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScanMode(StrEnum):
    """Scan profiles selectable by the user."""

    QUICK = "quick"
    DEEP = "deep"
    CUSTOM = "custom"


class ScanStatus(StrEnum):
    """Lifecycle status of a scan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModuleStatus(StrEnum):
    """Outcome of a single module execution within a scan."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class TaskState(StrEnum):
    """Lifecycle states for scheduler tasks."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
