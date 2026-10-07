"""Scan module system (Phase 7).

Collectors subclass :class:`modules.base.BaseModule`; the
:class:`modules.registry.ModuleRegistry` discovers and curates them, and the
engine plans eligible instances against the target.
"""

from modules.base import BaseModule, retry, run_with_timeout
from modules.registry import ModuleInfo, ModuleRegistry

__all__ = [
    "BaseModule",
    "ModuleInfo",
    "ModuleRegistry",
    "retry",
    "run_with_timeout",
]
