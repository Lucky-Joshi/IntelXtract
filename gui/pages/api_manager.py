"""API Manager page: provider keys stored in the encrypted vault (S24.4)."""

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

from core.exceptions import VaultError
from core.vault import delete_key, list_stored, mask, store_key
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
    return mask(value)


class ApiManagerPage(Page):
    """Encrypted (Fernet) API-key storage backed by the SQLite vault."""

    page_id = "api_manager"
    title = "API Manager"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        banner = QLabel(
            "Keys are encrypted with Fernet and stored in the vault (ciphertext "
            "only). The vault key resolves from INTELXTRACT_VAULT_KEY, the OS "
            "keyring, or a 0600 key file."
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

    def _stored_hints(self) -> dict[str, str]:
        try:
            return {
                row["provider"]: row["hint"] for row in list_stored(self.ctx.config)
            }
        except VaultError:
            return {}

    def refresh(self) -> None:
        section = self.ctx.config.section("api_keys")
        hints = self._stored_hints()
        providers = list(PROVIDERS)
        for name in {*section, *hints}:
            if name not in providers:
                providers.append(name)
        self.table.setRowCount(len(providers))
        configured = 0
        for row_idx, provider in enumerate(providers):
            hint = hints.get(provider) or mask(str(section.get(provider, "") or ""))
            is_set = bool(section.get(provider) or hint)
            configured += 1 if is_set else 0
            values = (provider, "yes" if is_set else "no", hint)
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, provider)
                self.table.setItem(row_idx, col, item)
        self.set_status(f"{configured} key(s) stored in the vault")

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
        try:
            hint = store_key(self.ctx.config, provider, value)
        except VaultError as exc:
            self.set_status(f"could not store key: {exc}")
            return
        self.key_input.clear()
        self.refresh()
        self.set_status(f"key for {provider} encrypted and stored ({hint})")

    def _clear(self) -> None:
        provider = self.provider_input.text().strip().lower()
        if not provider:
            self.set_status("enter the provider to clear")
            return
        try:
            delete_key(self.ctx.config, provider)
        except VaultError as exc:
            self.set_status(f"clear skipped: {exc}")
            return
        self.refresh()
        self.set_status(f"key for {provider} cleared")
