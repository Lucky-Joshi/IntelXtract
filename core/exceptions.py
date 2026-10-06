"""IntelXtract exception hierarchy.

Every library-level failure derives from :class:`IntelXtractError` so callers
can distinguish expected failures from programming errors.
"""

from __future__ import annotations


class IntelXtractError(Exception):
    """Base class for all IntelXtract errors."""


class ConfigError(IntelXtractError):
    """Invalid, unreadable, or unserializable configuration."""


class ValidationError(IntelXtractError):
    """User input (target, option, argument) failed validation."""


class DatabaseError(IntelXtractError):
    """Database connectivity or query failure."""


class MigrationError(DatabaseError):
    """Schema migration failed or schema is incompatible."""


class ModuleError(IntelXtractError):
    """An OSINT module failed while collecting a target."""

    def __init__(self, message: str, *, module: str | None = None) -> None:
        super().__init__(message)
        self.module = module


class ModuleTimeoutError(ModuleError):
    """A module exceeded its execution deadline."""


class PluginError(IntelXtractError):
    """A plugin is invalid or misbehaved."""

    def __init__(self, message: str, *, plugin: str | None = None) -> None:
        super().__init__(message)
        self.plugin = plugin


class PluginLoadError(PluginError):
    """A plugin could not be imported or instantiated."""


class PluginVersionError(PluginError):
    """A plugin declares an unsupported api_version."""


class ScanError(IntelXtractError):
    """A scan-level failure."""


class TaskTimeoutError(ScanError):
    """A scheduler task exceeded its timeout."""


class ScanCancelledError(ScanError):
    """A scan or task was cancelled."""
