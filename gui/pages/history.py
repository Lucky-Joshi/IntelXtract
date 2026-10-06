"""History page: past scans with filters and a diff entry point stub."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from gui import db_sync
from gui.pages.base import Page

_STATUSES = ("", "completed", "failed", "cancelled", "running", "pending")


class HistoryPage(Page):
    """Browse persisted scans and open one in Results."""

    page_id = "history"
    title = "History"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Target"))
        self.target_filter = QLineEdit()
        self.target_filter.setPlaceholderText("filter by target…")
        filters.addWidget(self.target_filter, stretch=1)
        filters.addWidget(QLabel("Status"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("any", "")
        for status in _STATUSES[1:]:
            self.status_filter.addItem(status, status)
        filters.addWidget(self.status_filter)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        filters.addWidget(refresh)
        open_btn = QPushButton("Open in Results")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self._open_selected)
        filters.addWidget(open_btn)
        diff = QPushButton("Diff…")
        diff.setObjectName("secondary")
        diff.clicked.connect(
            lambda: self.set_status("scan diff view lands in a later phase")
        )
        filters.addWidget(diff)
        self.body.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["id", "target", "type", "mode", "status", "started"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._open_selected)
        self.body.addWidget(self.table, stretch=1)

    def refresh(self) -> None:
        target = self.target_filter.text().strip() or None
        status = self.status_filter.currentData() or None
        scans = db_sync.recent_scans(
            self.ctx.db_path, limit=100, target=target, status=status
        )
        self.table.setRowCount(len(scans))
        for row_idx, scan in enumerate(scans):
            values = (
                str(scan.get("id", "")),
                str(scan.get("target", "")),
                str(scan.get("type", "")),
                str(scan.get("mode", "")),
                str(scan.get("status", "")),
                str(scan.get("started_at", "")),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, scan.get("id"))
                self.table.setItem(row_idx, col, item)
        self.set_status(f"{len(scans)} scan(s)")

    def _open_selected(self, *_args: Any) -> None:
        items = self.table.selectedItems()
        if not items:
            self.set_status("select a scan first")
            return
        row = items[0].row()
        item = self.table.item(row, 0)
        scan_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if scan_id is None:
            self.set_status("scan row has no id")
            return
        payload = db_sync.build_scan_payload(self.ctx.db_path, int(scan_id))
        if payload is None:
            self.set_status(f"scan not found: {scan_id}")
            return
        self.ctx.show_results(payload)
