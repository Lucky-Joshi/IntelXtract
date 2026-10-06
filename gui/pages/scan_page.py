"""Shared scan form: target input, run button, live module-run table."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.pages.base import Page

_RUN_COLS = ("module", "status", "duration (s)", "error")


class ScanPage(Page):
    """Quick/deep scan form wired to the engine bridge."""

    mode: str = "quick"
    with_checklist: bool = False

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._running = False

        form = QHBoxLayout()
        form.setSpacing(8)
        label = QLabel("Target")
        label.setObjectName("caption")
        form.addWidget(label)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("example.com, 1.2.3.4, https://…")
        self.target_input.setObjectName("target-input")
        form.addWidget(self.target_input, stretch=1)
        self.run_button = QPushButton("Run scan")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self._start)
        form.addWidget(self.run_button)
        self.body.addLayout(form)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.body.addWidget(self.progress)

        self.checklist_box: QWidget | None = None
        self.checklist: dict[str, QCheckBox] = {}
        if self.with_checklist:
            self._build_checklist()

        section = QLabel("Module runs")
        section.setObjectName("section")
        self.body.addWidget(section)

        self.runs_table = QTableWidget(0, len(_RUN_COLS))
        self.runs_table.setHorizontalHeaderLabels(list(_RUN_COLS))
        self.runs_table.verticalHeader().setVisible(False)
        self.runs_table.setAlternatingRowColors(True)
        self.runs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.runs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.body.addWidget(self.runs_table, stretch=1)

        bridge = self.ctx.bridge
        queued = Qt.ConnectionType.QueuedConnection
        bridge.module_finished.connect(self._on_module_finished, queued)
        bridge.scan_finished.connect(self._on_scan_finished, queued)
        bridge.scan_failed.connect(self._on_scan_failed, queued)
        bridge.scan_started.connect(self._on_scan_started, queued)
        bridge.modules_ready.connect(self._on_modules_ready, queued)

    def _build_checklist(self) -> None:
        from PySide6.QtWidgets import QGroupBox

        box = QGroupBox("Modules (custom selection)")
        layout = QVBoxLayout(box)
        self._checklist_layout = QVBoxLayout()
        self._checklist_layout.setSpacing(6)
        layout.addLayout(self._checklist_layout)
        self._checklist_note = QLabel("no modules registered yet (Phase 6+)")
        self._checklist_note.setObjectName("muted")
        layout.addWidget(self._checklist_note)
        self.checklist_box = box
        self.body.addWidget(box)

    def refresh(self) -> None:
        self.ctx.bridge.request_modules()

    def _checked_modules(self) -> list[str] | None:
        if not self.with_checklist:
            return None
        names = [name for name, box in self.checklist.items() if box.isChecked()]
        return names or None

    def _start(self) -> None:
        target = self.target_input.text().strip()
        if not target:
            self.set_status("target must not be empty")
            return
        self.runs_table.setRowCount(0)
        self._set_running(True)
        self.set_status(f"starting {self.mode} scan of {target}…")
        self.ctx.bridge.request_scan(target, self.mode, self._checked_modules())

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.setEnabled(not running)
        self.progress.setVisible(running)
        if running:
            self.progress.setRange(0, 0)

    def _on_scan_started(self, target: str, mode: str) -> None:
        if self._running:
            self.set_status(f"scanning {target} ({mode})…")

    def _on_module_finished(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        row = self.runs_table.rowCount()
        self.runs_table.insertRow(row)
        values = (
            str(payload.get("module", "")),
            str(payload.get("status", "")),
            str(payload.get("duration", "")),
            str(payload.get("error") or ""),
        )
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.runs_table.setItem(row, col, item)

    def _on_scan_finished(self, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        self._set_running(False)
        status = str(payload.get("status", "completed"))
        duration = payload.get("duration", 0.0)
        self.set_status(f"scan finished: {status} ({duration:.2f}s)")

    def _on_scan_failed(self, message: str) -> None:
        if not self._running:
            return
        self._set_running(False)
        self.set_status(f"scan failed: {message}")

    def _on_modules_ready(self, names: list) -> None:
        if not self.with_checklist or self.checklist_box is None:
            return
        existing = set(self.checklist)
        if set(names) == existing:
            return
        for box in self.checklist.values():
            self._checklist_layout.removeWidget(box)
            box.deleteLater()
        self.checklist.clear()
        self._checklist_note.setVisible(not names)
        for name in names:
            box = QCheckBox(str(name))
            box.setChecked(True)
            self.checklist[str(name)] = box
            self._checklist_layout.addWidget(box)
