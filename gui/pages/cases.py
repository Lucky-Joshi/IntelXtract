"""Cases page: group scans/notes into investigations with combined findings."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from gui import case_sync
from gui.pages.base import Page


class CasesPage(Page):
    """Create cases, attach scans, add notes, and review combined findings."""

    page_id = "cases"
    title = "Cases"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        create_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("case name")
        create_row.addWidget(self.name_input, stretch=2)
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("description (optional)")
        create_row.addWidget(self.desc_input, stretch=3)
        create_btn = QPushButton("Create case")
        create_btn.setObjectName("primary")
        create_btn.clicked.connect(self._create)
        create_row.addWidget(create_btn)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        create_row.addWidget(refresh)
        self.body.addLayout(create_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["id", "name", "status", "notes", "evidence", "created"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_details)
        self.body.addWidget(self.table, stretch=1)

        case_actions = QHBoxLayout()
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("note text")
        case_actions.addWidget(self.note_input, stretch=3)
        note_btn = QPushButton("Add note")
        note_btn.setObjectName("secondary")
        note_btn.clicked.connect(self._add_note)
        case_actions.addWidget(note_btn)
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("scan id to attach")
        case_actions.addWidget(self.scan_input, stretch=1)
        attach_btn = QPushButton("Attach scan")
        attach_btn.setObjectName("secondary")
        attach_btn.clicked.connect(self._attach_scan)
        case_actions.addWidget(attach_btn)
        self.body.addLayout(case_actions)

        self.notes_table = QTableWidget(0, 2)
        self.notes_table.setHorizontalHeaderLabels(["created", "note"])
        self._init_table(self.notes_table)
        self.body.addWidget(self.notes_table, stretch=1)

        self.findings_table = QTableWidget(0, 4)
        self.findings_table.setHorizontalHeaderLabels(
            ["id", "module", "severity", "title"]
        )
        self._init_table(self.findings_table)
        self.body.addWidget(self.findings_table, stretch=1)

        self.detail_label = QLabel("select a case to view notes and evidence")
        self.detail_label.setObjectName("muted")
        self.detail_label.setWordWrap(True)
        self.body.addWidget(self.detail_label)

    @staticmethod
    def _init_table(table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def refresh(self) -> None:
        cases = case_sync.list_cases(self.ctx.db_path)
        self.table.setRowCount(len(cases))
        for row_idx, case in enumerate(cases):
            values = (
                str(case.get("id", "")),
                str(case.get("name", "")),
                str(case.get("status", "")),
                str(case.get("note_count", 0)),
                str(case.get("evidence_count", 0)),
                str(case.get("created_at", "")),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, item)
        self._load_details()
        self.set_status(f"{len(cases)} case(s)")

    def _selected_case_id(self) -> int | None:
        items = self.table.selectedItems()
        if not items:
            return None
        item = self.table.item(items[0].row(), 0)
        if item is None:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    def _load_details(self) -> None:
        case_id = self._selected_case_id()
        if case_id is None:
            self.notes_table.setRowCount(0)
            self.findings_table.setRowCount(0)
            self.detail_label.setText("select a case to view notes and evidence")
            return

        notes = case_sync.list_notes(self.ctx.db_path, case_id)
        self.notes_table.setRowCount(len(notes))
        for row_idx, note in enumerate(notes):
            for col, value in enumerate(
                (str(note.get("created_at", "")), str(note.get("body", "")))
            ):
                self.notes_table.setItem(row_idx, col, QTableWidgetItem(value))

        findings = case_sync.case_findings(self.ctx.db_path, case_id)
        self.findings_table.setRowCount(len(findings))
        for row_idx, finding in enumerate(findings):
            values = (
                str(finding.get("id", "")),
                str(finding.get("module", "")),
                str(finding.get("severity") or "-"),
                str(finding.get("title") or ""),
            )
            for col, value in enumerate(values):
                self.findings_table.setItem(row_idx, col, QTableWidgetItem(value))

        evidence = case_sync.list_evidence(self.ctx.db_path, case_id)
        self.detail_label.setText(
            f"case #{case_id}: {len(notes)} note(s), {len(evidence)} evidence row(s), "
            f"{len(findings)} combined finding(s)"
        )

    def _create(self) -> None:
        try:
            case_id = case_sync.create_case(
                self.ctx.db_path, self.name_input.text(), self.desc_input.text()
            )
        except ValueError as exc:
            self.set_status(str(exc))
            return
        self.name_input.clear()
        self.desc_input.clear()
        self.refresh()
        self._select_case(case_id)
        self.set_status(f"case #{case_id} created")

    def _add_note(self) -> None:
        case_id = self._selected_case_id()
        if case_id is None:
            self.set_status("select a case first")
            return
        try:
            case_sync.add_note(self.ctx.db_path, case_id, self.note_input.text())
        except ValueError as exc:
            self.set_status(str(exc))
            return
        self.note_input.clear()
        self._load_details()
        self.set_status(f"note added to case #{case_id}")

    def _attach_scan(self) -> None:
        case_id = self._selected_case_id()
        if case_id is None:
            self.set_status("select a case first")
            return
        text = self.scan_input.text().strip()
        if not text.isdigit():
            self.set_status("enter a numeric scan id")
            return
        try:
            case_sync.attach_scan(self.ctx.db_path, case_id, int(text))
        except ValueError as exc:
            self.set_status(str(exc))
            return
        self.scan_input.clear()
        self.refresh()
        self._select_case(case_id)
        self.set_status(f"scan #{text} attached to case #{case_id}")

    def _select_case(self, case_id: int) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() == str(case_id):
                self.table.selectRow(row)
                return
