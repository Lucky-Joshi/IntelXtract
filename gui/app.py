"""GUI application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core.config import Config, load_config
from core.constants import APP_NAME
from core.engine import ScanModule
from core.logger import setup_logging
from gui.bridge import EngineBridge
from gui.main_window import MainWindow
from gui.theme import apply_theme


def create_window(
    config: Config | None = None,
    *,
    modules: list[ScanModule] | None = None,
) -> MainWindow:
    """Build the main window with logging and the engine bridge wired."""
    cfg = config if config is not None else load_config()
    setup_logging(cfg)
    bridge = EngineBridge(cfg, modules=modules)
    return MainWindow(cfg, bridge)


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop application (respects ``QT_QPA_PLATFORM``)."""
    args = sys.argv if argv is None else argv
    app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    apply_theme(app)
    window = create_window()
    window.show()
    return int(app.exec())
