"""Dashboard: stats, recent scans, plugin status, log tail."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.plugin_loader import PluginRegistry
from gui import db_sync
from gui.pages.base import Page

_STAT_KEYS = ("completed", "failed", "running", "cancelled", "pending")


class DashboardPage(Page):
    """Live overview assembled from the database, plugins, and log file."""

    page_id = "dashboard"
    title = "Dashboard"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)

        top = QHBoxLayout()
        self.stat_labels: dict[str, QLabel] = {}
        for key in _STAT_KEYS:
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            value = QLabel("0")
            value.setObjectName("stat-value")
            name = QLabel(key)
            name.setObjectName("stat-label")
            card_layout.addWidget(value)
            card_layout.addWidget(name)
            self.stat_labels[key] = value
            top.addWidget(card, stretch=1)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        self.body.addLayout(top)

        row = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self._section("Recent scans"))
        self.scans_table = QTableWidget(0, 5)
        self.scans_table.setHorizontalHeaderLabels(
            ["id", "target", "mode", "status", "started"]
        )
        self.scans_table.verticalHeader().setVisible(False)
        self.scans_table.setAlternatingRowColors(True)
        self.scans_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left.addWidget(self.scans_table)
        self.plugin_label = QLabel("plugins: 0")
        self.plugin_label.setObjectName("muted")
        left.addWidget(self.plugin_label)
        self.api_label = QLabel("api keys configured: 0")
        self.api_label.setObjectName("muted")
        left.addWidget(self.api_label)
        row.addLayout(left, stretch=3)

        right = QVBoxLayout()
        right.addWidget(self._section("Log tail"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("log-tail")
        right.addWidget(self.log_view)
        row.addLayout(right, stretch=2)
        self.body.addLayout(row)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def refresh(self) -> None:
        stats = db_sync.scan_stats(self.ctx.db_path)
        for key, label in self.stat_labels.items():
            label.setText(str(stats.get(key, 0)))

        scans = db_sync.recent_scans(self.ctx.db_path, limit=10)
        self.scans_table.setRowCount(len(scans))
        for row_idx, scan in enumerate(scans):
            values = (
                str(scan.get("id", "")),
                str(scan.get("target", "")),
                str(scan.get("mode", "")),
                str(scan.get("status", "")),
                str(scan.get("started_at", "")),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.scans_table.setItem(row_idx, col, item)

        registry = PluginRegistry(
            Path(str(self.ctx.config.get("paths.plugins_dir", "plugins"))).expanduser()
        )
        plugins = registry.discover()
        enabled = sum(1 for info in plugins if info.error is None)
        self.plugin_label.setText(f"plugins: {len(plugins)} discovered, {enabled} ok")

        api_keys = self.ctx.config.section("api_keys")
        self.api_label.setText(f"api keys configured: {len(api_keys)}")

        log_path = Path(str(self.ctx.config.get("logging.file", ""))).expanduser()
        self.log_view.setPlainText(self._tail(log_path))

    @staticmethod
    def _tail(path: Path, lines: int = 40) -> str:
        if not path.is_file():
            return "(no log file yet)"
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "(log file unreadable)"
        parts = content.splitlines()
        return "\n".join(parts[-lines:]) if parts else "(log file empty)"
