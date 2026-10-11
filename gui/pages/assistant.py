"""Assistant page: opt-in, grounded AI answers about a past scan.

The underlying provider is disabled by default. Answers are always labeled
AI-generated and kept visually separate from scan findings.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
)

from assistant import Assistant
from assistant.service import DISABLED_WARNING
from gui import db_sync
from gui.pages.base import Page
from reports import build_report


def _report_model(payload: dict[str, Any]) -> Any:
    """Build a report model from a GUI scan payload (parsing JSON data cells)."""
    findings: list[dict[str, Any]] = []
    for row in payload.get("findings", []):
        data = row.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        findings.append({**row, "data": data})
    return build_report(payload["scan"], payload["target"], findings)


class AssistantPage(Page):
    """Ask the optional assistant to summarize a scan or suggest next steps."""

    page_id = "assistant"
    title = "Assistant"

    _answer_ready = Signal(dict)
    _answer_failed = Signal(str)

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)
        self._assistant = Assistant(ctx.config)
        self._answer_ready.connect(self._on_answer)
        self._answer_failed.connect(self._on_failure)

        self.banner = QLabel("")
        self.banner.setObjectName("muted")
        self.banner.setWordWrap(True)
        self.body.addWidget(self.banner)

        row = QHBoxLayout()
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("scan id")
        row.addWidget(self.scan_input, stretch=1)
        self.kind = QComboBox()
        self.kind.addItems(["summary", "next-steps"])
        row.addWidget(self.kind)
        self.ask_button = QPushButton("Ask")
        self.ask_button.setObjectName("primary")
        self.ask_button.clicked.connect(self._ask)
        row.addWidget(self.ask_button)
        self.body.addLayout(row)

        self.output_label = QLabel("")
        self.output_label.setObjectName("muted")
        self.output_label.setWordWrap(True)
        self.body.addWidget(self.output_label)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.body.addWidget(self.output, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        """Reflect the current enabled/disabled provider state."""
        if self._assistant.enabled:
            self.banner.setText(
                f"Enabled — provider: {self._assistant.provider_name}. Report "
                "content is sent off this machine. Answers are AI-generated and "
                "are not scan findings."
            )
            self.set_status("ready")
        else:
            self.banner.setText(DISABLED_WARNING)
            self.set_status("assistant disabled")
        self.ask_button.setEnabled(self._assistant.enabled)

    def _ask(self) -> None:
        text = self.scan_input.text().strip()
        if not text.isdigit():
            self.set_status("enter a numeric scan id")
            return
        payload = db_sync.build_scan_payload(self.ctx.db_path, int(text))
        if payload is None:
            self.set_status(f"scan #{text} not found")
            return
        model = _report_model(payload)
        kind = self.kind.currentText()
        assistant = self._assistant
        self.ask_button.setEnabled(False)
        self.set_status("asking the assistant…")

        def worker() -> None:
            try:
                if kind == "next-steps":
                    answer = asyncio.run(assistant.suggest_next_steps(model))
                else:
                    answer = asyncio.run(assistant.summarize(model))
            except Exception as exc:  # surface any provider/runtime failure
                self._answer_failed.emit(str(exc))
                return
            self._answer_ready.emit(answer.to_dict())

        threading.Thread(target=worker, daemon=True).start()

    def _on_answer(self, answer: dict[str, Any]) -> None:
        warning = answer.get("warning")
        if warning:
            self.set_status(str(warning))
        else:
            model = answer.get("model") or "-"
            self.set_status(f"{answer.get('provider')} · {model}")
        label = str(answer.get("label", "AI-generated"))
        self.output_label.setText(
            f"{label} — not a scan finding; verify independently."
        )
        self.output.setPlainText(str(answer.get("text", "")))

    def _on_failure(self, message: str) -> None:
        self.set_status(message)
        self.ask_button.setEnabled(self._assistant.enabled)
