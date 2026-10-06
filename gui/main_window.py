"""Main window: sidebar navigation, stacked pages, status bar."""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.constants import APP_NAME, VERSION
from gui.bridge import EngineBridge
from gui.context import GuiContext
from gui.pages import (
    AboutPage,
    ApiManagerPage,
    DashboardPage,
    DeepScanPage,
    HistoryPage,
    Page,
    PluginsPage,
    QuickScanPage,
    ReportsPage,
    ResultsPage,
    SettingsPage,
)

_NAV: tuple[tuple[str, str], ...] = (
    ("dashboard", "Dashboard"),
    ("quick_scan", "Quick Scan"),
    ("deep_scan", "Deep Scan"),
    ("results", "Results"),
    ("reports", "Reports"),
    ("history", "History"),
    ("plugins", "Plugins"),
    ("api_manager", "API Manager"),
    ("settings", "Settings"),
    ("about", "About"),
)


class MainWindow(QMainWindow):
    """Application shell hosting every stubbed page."""

    def __init__(self, config: Config, bridge: EngineBridge) -> None:
        super().__init__()
        self._config = config
        self._bridge = bridge
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1180, 760)

        self.ctx = GuiContext(
            config=config,
            bridge=bridge,
            db_path=bridge.db_path,
            show_results=self.show_results,
        )

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(0, 0, 0, 12)
        side_layout.setSpacing(0)

        app_title = QLabel(APP_NAME)
        app_title.setObjectName("app-title")
        side_layout.addWidget(app_title)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages: dict[str, Page] = {}
        self.stacked = QStackedWidget()

        page_types: dict[str, type[Page]] = {
            "dashboard": DashboardPage,
            "quick_scan": QuickScanPage,
            "deep_scan": DeepScanPage,
            "results": ResultsPage,
            "reports": ReportsPage,
            "history": HistoryPage,
            "plugins": PluginsPage,
            "api_manager": ApiManagerPage,
            "settings": SettingsPage,
            "about": AboutPage,
        }
        for page_id, label in _NAV:
            button = QPushButton(label)
            button.setObjectName("nav-button")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(button)
            self.nav_buttons[page_id] = button
            side_layout.addWidget(button)
            page = page_types[page_id](self.ctx)
            self.pages[page_id] = page
            self.stacked.addWidget(page)
            button.clicked.connect(
                lambda _checked=False, pid=page_id: self.switch_page(pid)
            )
        side_layout.addStretch(1)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stacked, stretch=1)
        self.setCentralWidget(central)

        self._status_label = QLabel("")
        self._version_label = QLabel(f"v{VERSION}")
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        status.addPermanentWidget(self._status_label)
        status.addPermanentWidget(self._version_label)
        self.setStatusBar(status)

        queued = Qt.ConnectionType.QueuedConnection
        bridge.scan_started.connect(self._on_scan_started, queued)
        bridge.scan_finished.connect(self._on_scan_finished, queued)
        bridge.scan_failed.connect(self._on_scan_failed, queued)

        self.switch_page("dashboard")

    @property
    def bridge(self) -> EngineBridge:
        """Engine bridge owned by this window."""
        return self._bridge

    def page(self, page_id: str) -> Page:
        """Return a page by id."""
        return self.pages[page_id]

    def switch_page(self, page_id: str) -> None:
        """Activate a page and refresh its data."""
        page = self.pages[page_id]
        self.stacked.setCurrentWidget(page)
        button = self.nav_buttons[page_id]
        button.setChecked(True)
        page.refresh()
        self.statusBar().showMessage(page.title)

    def show_results(self, payload: dict[str, Any]) -> None:
        """Render a result payload on the Results page and navigate to it."""
        page = cast(ResultsPage, self.pages["results"])
        page.show_result(payload)
        self.switch_page("results")

    def _on_scan_started(self, target: str, mode: str) -> None:
        self._status_label.setText(f"scanning {target} ({mode})…")

    def _on_scan_finished(self, payload: dict[str, Any]) -> None:
        status = str(payload.get("status", "completed"))
        self._status_label.setText(f"scan {status}")
        current = self.stacked.currentWidget()
        if isinstance(current, Page):
            current.refresh()

    def _on_scan_failed(self, message: str) -> None:
        self._status_label.setText(f"scan failed: {message}")

    def closeEvent(self, event: Any) -> None:
        """Shut the engine bridge down before closing."""
        self._bridge.shutdown()
        super().closeEvent(event)
