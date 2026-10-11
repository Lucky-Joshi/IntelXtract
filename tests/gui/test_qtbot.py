"""pytest-qt driven offscreen GUI tests (S26.5): navigation, scan, results."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import Qt

from core.constants import TargetType

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")


class DummyModule:
    """Minimal ScanModule stand-in mirroring ``test_smoke``."""

    name = "dummy"
    target_types: tuple[TargetType, ...] = ()

    def validate(self, target: str) -> bool:
        return bool(target and target.strip())

    async def run(self, target: str, ctx: Any) -> dict[str, Any]:
        return {"echo": target}


def test_qtbot_page_navigation(make_window: Any, qtbot: Any) -> None:
    window = make_window()
    qtbot.addWidget(window)
    for page_id, button in window.nav_buttons.items():
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda pid=page_id: window.stacked.currentWidget() is window.page(pid),
            timeout=2000,
        )


def test_qtbot_quick_scan_starts_and_renders_results(
    make_window: Any, qtbot: Any, gui_env: Any
) -> None:
    window = make_window(modules=[DummyModule()])
    qtbot.addWidget(window)
    window.switch_page("quick_scan")
    page = window.page("quick_scan")
    page.target_input.setText("qtbot.test")
    qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)

    results = window.page("results")
    qtbot.waitUntil(lambda: results.target_label.text() == "qtbot.test", timeout=8000)
    qtbot.waitUntil(lambda: results.runs_table.rowCount() >= 1, timeout=8000)
