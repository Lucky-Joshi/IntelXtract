"""Base page widget shared by every GUI page."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from gui.context import GuiContext


class Page(QWidget):
    """One sidebar page: title header, body layout, status line."""

    page_id: str = ""
    title: str = ""

    def __init__(self, ctx: GuiContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(24, 20, 24, 16)
        self._root.setSpacing(12)

        header = QLabel(self.title)
        header.setObjectName("title")
        self._root.addWidget(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self._root.addLayout(self.body)

        self.body.addStretch(1)
        self._status = QLabel("")
        self._status.setObjectName("muted")
        self._status.setWordWrap(True)
        self._root.addWidget(self._status)

    def set_status(self, text: str) -> None:
        """Update the page status line."""
        self._status.setText(text)

    def refresh(self) -> None:
        """Called whenever the page is shown; override to reload data."""
