"""Shared GUI application context handed to every page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.config import Config
from gui.bridge import EngineBridge


@dataclass
class GuiContext:
    """Everything a page needs to talk to core services."""

    config: Config
    bridge: EngineBridge
    db_path: str
    show_results: Callable[[dict[str, Any]], None]
