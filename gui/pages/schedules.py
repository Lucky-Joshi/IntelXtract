"""Schedules page: recurring scans and their next run times."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from gui import db_sync
from gui.pages.base import Page


class SchedulesPage(Page):
    """Read-only view of configured recurring scans."""

    page_id = "schedules"
    title = "Schedules"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        controls = QHBoxLayout()
        controls.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(refresh)
        self.body.addLayout(controls)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["id", "target", "mode", "cadence", "enabled", "status", "next run"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.body.addWidget(self.table, stretch=1)

    def refresh(self) -> None:
        rows = db_sync.list_schedules(self.ctx.db_path)
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = (
                str(row.get("id", "")),
                str(row.get("target", "")),
                str(row.get("mode", "")),
                self._cadence(row),
                "yes" if row.get("enabled") else "no",
                str(row.get("status", "")),
                str(row.get("next_run_at") or "-"),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, item)
        self.set_status(f"{len(rows)} schedule(s)")

    @staticmethod
    def _cadence(row: dict[str, Any]) -> str:
        cron = row.get("cron")
        if cron:
            return f"cron {cron}"
        interval = row.get("interval_seconds")
        return f"{interval}s" if interval else "-"
