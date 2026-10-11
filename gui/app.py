"""GUI application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core.config import Config, load_config
from core.constants import APP_NAME
from core.engine import ScanModule
from core.exceptions import VaultError
from core.logger import setup_logging
from core.vault import hydrate_api_keys
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
    try:
        hydrate_api_keys(cfg)
    except VaultError:
        pass
    setup_logging(cfg)
    bridge = EngineBridge(cfg, modules=modules)
    return MainWindow(cfg, bridge)


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop application (respects ``QT_QPA_PLATFORM``)."""
    args = sys.argv if argv is None else argv
    app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    cfg = load_config()
    apply_theme(app, str(cfg.get("gui.theme", "dark")))
    window = create_window(cfg)
    window.show()
    return int(app.exec())
