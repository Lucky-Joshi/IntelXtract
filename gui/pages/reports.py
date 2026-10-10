"""Reports page: generated report files with export stubs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from gui import db_sync
from gui.pages.base import Page


class ReportsPage(Page):
    """Lists reports registered in the database."""

    page_id = "reports"
    title = "Reports"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        actions = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        stub = QPushButton("Export…")
        stub.setObjectName("secondary")
        stub.clicked.connect(
            lambda: self.set_status(
                "full export shortcuts arrive with report formats (Phase 19)"
            )
        )
        actions.addWidget(stub)
        actions.addStretch(1)
        self.body.addLayout(actions)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["id", "scan id", "format", "path"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.body.addWidget(self.table, stretch=1)

        note = QLabel(
            "Generate reports from the CLI: `intelxtract report <id> "
            "--format json|html|pdf|csv|md`."
        )
        note.setObjectName("muted")
        self.body.addWidget(note)

    def refresh(self) -> None:
        reports = db_sync.list_reports(self.ctx.db_path)
        self.table.setRowCount(len(reports))
        for row_idx, report in enumerate(reports):
            values = (
                str(report.get("id", "")),
                str(report.get("scan_id", "")),
                str(report.get("format", "")),
                str(report.get("path", "")),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, item)
        self.set_status(f"{len(reports)} report(s)")
