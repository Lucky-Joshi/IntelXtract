"""API Manager page: provider keys stored in config (vault lands Phase 24)."""

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

from gui.pages.base import Page

PROVIDERS: tuple[str, ...] = (
    "shodan",
    "virustotal",
    "censys",
    "securitytrails",
    "emailrep",
    "hunter",
    "github",
    "abuseipdb",
)


def mask_key(value: str) -> str:
    """Render a stored key without revealing it."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"{value[:2]}••••{value[-2:]}"


class ApiManagerPage(Page):
    """Interim config-backed API key storage with a vault warning banner."""

    page_id = "api_manager"
    title = "API Manager"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        banner = QLabel(
            "Interim storage: keys are written to config/settings.json in plain "
            "text. Encrypted vault storage arrives in Phase 24."
        )
        banner.setObjectName("banner")
        banner.setWordWrap(True)
        self.body.addWidget(banner)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["provider", "configured", "value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.body.addWidget(self.table, stretch=1)

        form = QHBoxLayout()
        form.addWidget(QLabel("Provider"))
        self.provider_input = QLineEdit()
        self.provider_input.setPlaceholderText("shodan")
        form.addWidget(self.provider_input, stretch=1)
        form.addWidget(QLabel("Key"))
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("API key value")
        form.addWidget(self.key_input, stretch=2)
        save_btn = QPushButton("Save key")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        form.addWidget(save_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self._clear)
        form.addWidget(clear_btn)
        self.body.addLayout(form)

    def refresh(self) -> None:
        section = self.ctx.config.section("api_keys")
        providers = list(PROVIDERS)
        for name in section:
            if name not in providers:
                providers.append(name)
        self.table.setRowCount(len(providers))
        for row_idx, provider in enumerate(providers):
            value = str(section.get(provider, "") or "")
            values = (
                provider,
                "yes" if value else "no",
                mask_key(value),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, provider)
                self.table.setItem(row_idx, col, item)
        self.set_status(f"{sum(1 for p in providers if section.get(p))} key(s) stored")

    def _on_select(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        provider = items[0].data(Qt.ItemDataRole.UserRole)
        if provider:
            self.provider_input.setText(str(provider))

    def _save(self) -> None:
        provider = self.provider_input.text().strip().lower()
        value = self.key_input.text().strip()
        if not provider or not value:
            self.set_status("provider and key are both required")
            return
        self.ctx.config.set(f"api_keys.{provider}", value)
        try:
            self.ctx.config.save()
        except Exception as exc:
            self.set_status(f"could not save config: {exc}")
            return
        self.key_input.clear()
        self.refresh()
        self.set_status(f"key for {provider} stored in config")

    def _clear(self) -> None:
        provider = self.provider_input.text().strip().lower()
        if not provider:
            self.set_status("enter the provider to clear")
            return
        key = f"api_keys.{provider}"
        try:
            self.ctx.config.unset(key)
            self.ctx.config.save()
        except Exception as exc:
            self.set_status(f"clear skipped: {exc}")
            return
        self.refresh()
        self.set_status(f"key for {provider} cleared")
