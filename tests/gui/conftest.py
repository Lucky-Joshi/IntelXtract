"""GUI test fixtures: offscreen Qt, isolated config, window factory."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from core.engine import ScanModule
    from gui.main_window import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Shared QApplication for the whole test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return cast(QApplication, app)


@pytest.fixture
def gui_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every config knob at an isolated temp directory."""
    monkeypatch.setenv("INTELXTRACT_CONFIG_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setenv("INTELXTRACT_PATHS__DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("INTELXTRACT_PATHS__EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("INTELXTRACT_PATHS__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INTELXTRACT_PATHS__PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("INTELXTRACT_LOGGING__FILE", str(tmp_path / "app.log"))
    monkeypatch.setenv("INTELXTRACT_LOGGING__CONSOLE", "false")
    return tmp_path


@pytest.fixture
def make_window(
    qapp: QApplication, gui_env: Path
) -> Iterator[Callable[..., MainWindow]]:
    """Factory that creates windows and shuts their bridges down."""
    from core.config import load_config
    from gui.app import create_window

    created: list[MainWindow] = []

    def _make(*, modules: list[ScanModule] | None = None) -> MainWindow:
        cfg = load_config()
        window = create_window(cfg, modules=modules)
        created.append(window)
        return window

    yield _make
    for window in created:
        window.close()
        window.bridge.shutdown()
