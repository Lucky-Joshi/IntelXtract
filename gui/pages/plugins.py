"""Plugins page: discovered plugins, enable/disable, manifest details."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from core.plugin_loader import PluginInfo, PluginRegistry
from gui.pages.base import Page


class PluginsPage(Page):
    """Lists plugins from the configured plugins directory."""

    page_id = "plugins"
    title = "Plugins"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)
        self._registry = PluginRegistry(self._plugins_dir())
        self._infos: list[PluginInfo] = []

        actions = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        enable_btn = QPushButton("Enable")
        enable_btn.setObjectName("secondary")
        enable_btn.clicked.connect(lambda: self._toggle(True))
        actions.addWidget(enable_btn)
        disable_btn = QPushButton("Disable")
        disable_btn.setObjectName("secondary")
        disable_btn.clicked.connect(lambda: self._toggle(False))
        actions.addWidget(disable_btn)
        actions.addStretch(1)
        self.body.addLayout(actions)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["name", "version", "state", "path"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.body.addWidget(self.table, stretch=1)

        self.details = QLabel("select a plugin to view its manifest details")
        self.details.setObjectName("muted")
        self.details.setWordWrap(True)
        self.body.addWidget(self.details)

    def _plugins_dir(self) -> Path:
        return Path(
            str(self.ctx.config.get("paths.plugins_dir", "plugins"))
        ).expanduser()

    def refresh(self) -> None:
        self._infos = self._registry.discover()
        self.table.setRowCount(len(self._infos))
        for row_idx, info in enumerate(self._infos):
            if info.error is not None:
                state = "error"
            elif self._registry.is_enabled(info.name):
                state = "enabled"
            else:
                state = "disabled"
            values = (info.name, info.version, state, str(info.source))
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, item)
        self.set_status(f"{len(self._infos)} plugin(s) discovered")

    def _selected_info(self) -> PluginInfo | None:
        items = self.table.selectedItems()
        if not items or not self._infos:
            return None
        row = items[0].row()
        if row >= len(self._infos):
            return None
        return self._infos[row]

    def _show_details(self) -> None:
        info = self._selected_info()
        if info is None:
            return
        target_types = ", ".join(t.value for t in info.target_types) or "—"
        error = f"\nerror: {info.error}" if info.error else ""
        self.details.setText(
            f"{info.name} v{info.version} (api {info.api_version})\n"
            f"{info.description or 'no description'}\n"
            f"targets: {target_types}\n"
            f"source: {info.source}{error}"
        )

    def _toggle(self, enable: bool) -> None:
        info = self._selected_info()
        if info is None:
            self.set_status("select a plugin first")
            return
        try:
            if enable:
                self._registry.enable(info.name)
            else:
                self._registry.disable(info.name)
        except Exception as exc:
            self.set_status(str(exc))
            return
        self.refresh()
        self.set_status(f"plugin {info.name} {'enabled' if enable else 'disabled'}")
