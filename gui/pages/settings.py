"""Settings page: theme note, paths, scan, cache, and logging values."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from gui.pages.base import Page

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class SettingsPage(Page):
    """Edits dotted config keys and persists them to settings.json."""

    page_id = "settings"
    title = "Settings"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        note = QLabel(
            "Dark theme is applied from BRAND.md tokens. Light theme arrives post-1.0."
        )
        note.setObjectName("muted")
        self.body.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)

        self.db_path = QLineEdit()
        self.exports_dir = QLineEdit()
        self.plugins_dir = QLineEdit()
        self.logs_dir = QLineEdit()
        form.addRow("Database path", self.db_path)
        form.addRow("Exports directory", self.exports_dir)
        form.addRow("Plugins directory", self.plugins_dir)
        form.addRow("Logs directory", self.logs_dir)

        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1.0, 600.0)
        self.timeout.setDecimals(1)
        self.timeout.setSuffix(" s")
        self.max_workers = QSpinBox()
        self.max_workers.setRange(1, 64)
        form.addRow("Default scan timeout", self.timeout)
        form.addRow("Max scan workers", self.max_workers)

        self.cache_ttl = QDoubleSpinBox()
        self.cache_ttl.setRange(1.0, 86400.0)
        self.cache_ttl.setDecimals(1)
        self.cache_ttl.setSuffix(" s")
        self.cache_max = QSpinBox()
        self.cache_max.setRange(1, 100000)
        form.addRow("Cache TTL", self.cache_ttl)
        form.addRow("Cache max size", self.cache_max)

        self.log_level = QComboBox()
        self.log_level.addItems(list(_LOG_LEVELS))
        self.log_file = QLineEdit()
        form.addRow("Log level", self.log_level)
        form.addRow("Log file", self.log_file)

        self.body.addLayout(form)

        actions = QHBoxLayout()
        save_btn = QPushButton("Save settings")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        actions.addWidget(save_btn)
        reload_btn = QPushButton("Reload")
        reload_btn.setObjectName("secondary")
        reload_btn.clicked.connect(self.refresh)
        actions.addWidget(reload_btn)
        actions.addStretch(1)
        self.body.addLayout(actions)

    def refresh(self) -> None:
        cfg = self.ctx.config
        self.db_path.setText(str(cfg.get("paths.db_path", "")))
        self.exports_dir.setText(str(cfg.get("paths.exports_dir", "")))
        self.plugins_dir.setText(str(cfg.get("paths.plugins_dir", "")))
        self.logs_dir.setText(str(cfg.get("paths.logs_dir", "")))
        self.timeout.setValue(float(cfg.get("scan.default_timeout", 30.0)))
        self.max_workers.setValue(int(cfg.get("scan.max_workers", 8)))
        self.cache_ttl.setValue(float(cfg.get("cache.ttl", 300.0)))
        self.cache_max.setValue(int(cfg.get("cache.max_size", 1024)))
        level = str(cfg.get("logging.level", "INFO")).upper()
        index = self.log_level.findText(level)
        self.log_level.setCurrentIndex(max(index, 0))
        self.log_file.setText(str(cfg.get("logging.file", "")))
        self.set_status(f"editing {cfg.path}")

    def _save(self) -> None:
        cfg = self.ctx.config
        cfg.set("paths.db_path", self.db_path.text().strip())
        cfg.set("paths.exports_dir", self.exports_dir.text().strip())
        cfg.set("paths.plugins_dir", self.plugins_dir.text().strip())
        cfg.set("paths.logs_dir", self.logs_dir.text().strip())
        cfg.set("scan.default_timeout", float(self.timeout.value()))
        cfg.set("scan.max_workers", int(self.max_workers.value()))
        cfg.set("cache.ttl", float(self.cache_ttl.value()))
        cfg.set("cache.max_size", int(self.cache_max.value()))
        cfg.set("logging.level", self.log_level.currentText())
        cfg.set("logging.file", self.log_file.text().strip())
        try:
            cfg.save()
        except Exception as exc:
            self.set_status(f"could not save settings: {exc}")
            return
        self.set_status("settings saved")
