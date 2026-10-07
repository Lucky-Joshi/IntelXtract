"""Offscreen smoke tests for the GUI shell (S5.13)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from core.constants import TargetType
from gui.theme import COLORS, DARK_QSS

pytest.importorskip("PySide6")


class DummyModule:
    """Minimal ScanModule stand-in until the real module system lands."""

    name = "dummy"
    target_types: tuple[TargetType, ...] = ()

    def validate(self, target: str) -> bool:
        return bool(target and target.strip())

    async def run(self, target: str, ctx: Any) -> dict[str, Any]:
        return {"echo": target}


def wait_spy(spy: QSignalSpy, timeout_ms: int = 8000) -> bool:
    """Pump Qt events until ``spy`` fires or the timeout elapses.

    ``QSignalSpy.wait`` does not reliably deliver cross-thread queued
    signals in this Qt build, so tests drive the event loop directly.
    """
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if spy.count() > 0:
            return True
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    return spy.count() > 0


def wait_for(predicate: Any, timeout_ms: int = 8000) -> bool:
    """Pump Qt events until ``predicate()`` is truthy or the timeout elapses.

    Used instead of raw signal spies when the assertion depends on queued
    slots finishing (page handlers run after the spy may already have fired).
    """
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if predicate():
            return True
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    return bool(predicate())


def test_theme_contains_brand_tokens(qapp: Any) -> None:
    from gui.theme import apply_theme

    apply_theme(qapp)
    assert qapp.styleSheet() == DARK_QSS
    assert COLORS["bg"] in qapp.styleSheet()
    assert COLORS["accent"] in qapp.styleSheet()


def test_window_launches_and_every_page_opens(make_window: Any) -> None:
    window = make_window()
    expected = [
        "dashboard",
        "quick_scan",
        "deep_scan",
        "results",
        "reports",
        "history",
        "plugins",
        "api_manager",
        "settings",
        "about",
    ]
    assert list(window.pages) == expected
    for page_id in expected:
        window.switch_page(page_id)
        page = window.page(page_id)
        assert window.stacked.currentWidget() is page
        assert page.title


def test_navigation_clicking_sidebar(make_window: Any) -> None:
    window = make_window()
    for page_id, button in window.nav_buttons.items():
        button.click()
        assert window.stacked.currentWidget() is window.page(page_id)
        assert button.isChecked()


def test_quick_scan_completes_and_persists(make_window: Any, gui_env: Any) -> None:
    window = make_window(modules=[DummyModule()])
    window.switch_page("quick_scan")
    page = window.page("quick_scan")
    page.target_input.setText("example.com")
    spy = QSignalSpy(window.bridge.scan_finished)
    page.run_button.click()
    assert wait_spy(spy), "scan_finished was not emitted"
    payload = spy.at(0)[0]
    assert payload["status"] == "completed"
    assert payload["target"] == "example.com"
    assert any(run["module"] == "dummy" for run in payload["runs"])

    from gui import db_sync

    scans = db_sync.recent_scans(window.bridge.db_path)
    assert len(scans) == 1
    assert scans[0]["target"] == "example.com"
    assert scans[0]["status"] == "completed"

    window.switch_page("history")
    history = window.page("history")
    assert history.table.rowCount() == 1


def test_deep_scan_checklist_and_run(make_window: Any, gui_env: Any) -> None:
    window = make_window(modules=[DummyModule()])
    window.switch_page("deep_scan")
    page = window.page("deep_scan")
    page.refresh()
    assert wait_for(lambda: "dummy" in page.checklist)
    assert page.checklist["dummy"].isChecked()

    page.target_input.setText("1.2.3.4")
    page.run_button.click()
    assert wait_for(lambda: page.runs_table.rowCount() >= 1)

    from gui import db_sync

    scans = db_sync.recent_scans(window.bridge.db_path)
    assert scans, "deep scan did not persist"
    assert scans[0]["mode"] == "deep"


def test_results_page_receives_engine_payload(make_window: Any) -> None:
    window = make_window(modules=[DummyModule()])
    window.switch_page("quick_scan")
    page = window.page("quick_scan")
    page.target_input.setText("example.org")
    page.run_button.click()
    results = window.page("results")
    assert wait_for(lambda: results.target_label.text() == "example.org")
    assert results.runs_table.rowCount() >= 1


def test_history_open_in_results(make_window: Any) -> None:
    window = make_window(modules=[DummyModule()])
    window.switch_page("quick_scan")
    page = window.page("quick_scan")
    page.target_input.setText("open-me.test")
    spy = QSignalSpy(window.bridge.scan_finished)
    page.run_button.click()
    assert wait_spy(spy)

    window.switch_page("history")
    history = window.page("history")
    history.refresh()
    assert history.table.rowCount() == 1
    history.table.selectRow(0)
    history._open_selected()
    assert window.stacked.currentWidget() is window.page("results")
    assert window.page("results").target_label.text() == "open-me.test"


def test_settings_save_roundtrip(make_window: Any, gui_env: Any) -> None:
    from core.config import load_config

    window = make_window()
    window.switch_page("settings")
    page = window.page("settings")
    page.max_workers.setValue(16)
    page.timeout.setValue(45.5)
    page._save()
    assert "settings saved" in page._status.text()

    reloaded = load_config()
    assert int(reloaded.get("scan.max_workers")) == 16
    assert float(reloaded.get("scan.default_timeout")) == 45.5


def test_plugins_page_discovers_manifest(
    make_window: Any, gui_env: Any, tmp_path: Any
) -> None:
    plugins_dir = tmp_path / "plugins" / "demo"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "plugin.py").write_text(
        "from core.plugin_loader import PluginBase\n"
        "\n"
        "\n"
        "class DemoPlugin(PluginBase):\n"
        '    name = "demo"\n'
        '    version = "1.2.3"\n'
        '    description = "demo plugin"\n'
        "\n"
        "    async def run(self, target, ctx):\n"
        "        return {}\n",
        encoding="utf-8",
    )
    (plugins_dir / "manifest.json").write_text(
        '{"version": "1.2.3", "description": "demo plugin"}', encoding="utf-8"
    )

    window = make_window()
    window.switch_page("plugins")
    page = window.page("plugins")
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "demo"
    assert page.table.item(0, 2).text() == "enabled"

    page.table.selectRow(0)
    page._toggle(False)
    assert page.table.item(0, 2).text() == "disabled"


def test_api_manager_save_masks_key(make_window: Any, gui_env: Any) -> None:
    from core.config import load_config

    window = make_window()
    window.switch_page("api_manager")
    page = window.page("api_manager")
    page.provider_input.setText("shodan")
    page.key_input.setText("supersecretvalue")
    page._save()

    assert "supersecretvalue" not in page.table.item(0, 2).text()
    reloaded = load_config()
    assert reloaded.get("api_keys.shodan") == "supersecretvalue"


def test_dashboard_refresh_reads_db(make_window: Any) -> None:
    window = make_window(modules=[DummyModule()])
    window.switch_page("quick_scan")
    page = window.page("quick_scan")
    page.target_input.setText("dash.test")
    spy = QSignalSpy(window.bridge.scan_finished)
    page.run_button.click()
    assert wait_spy(spy)

    window.switch_page("dashboard")
    dashboard = window.page("dashboard")
    assert dashboard.stat_labels["completed"].text() == "1"
    assert dashboard.scans_table.rowCount() == 1
    assert dashboard.scans_table.item(0, 1).text() == "dash.test"
