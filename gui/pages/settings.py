"""Settings page: theme, network, paths, scan, cache, and logging values."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
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
_THEMES = ("dark",)
_LANGUAGES = ("en",)


class SettingsPage(Page):
    """Edits dotted config keys and persists them to settings.json."""

    page_id = "settings"
    title = "Settings"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        note = QLabel(
            "Dark theme is applied from BRAND.md tokens. Light theme arrives "
            "post-1.0. Telemetry is always off."
        )
        note.setObjectName("muted")
        self.body.addWidget(note)

        appearance = QFormLayout()
        appearance.setSpacing(10)
        self.theme = QComboBox()
        self.theme.addItems(list(_THEMES))
        self.language = QComboBox()
        self.language.addItems(list(_LANGUAGES))
        appearance.addRow("Theme", self.theme)
        appearance.addRow("Language", self.language)
        self.body.addLayout(appearance)

        network = QFormLayout()
        network.setSpacing(10)
        self.proxy = QLineEdit()
        self.proxy.setPlaceholderText("http://host:port (blank = direct)")
        self.rate_limit = QDoubleSpinBox()
        self.rate_limit.setRange(0.0, 100.0)
        self.rate_limit.setDecimals(1)
        self.rate_limit.setSuffix(" req/s")
        self.net_timeout = QDoubleSpinBox()
        self.net_timeout.setRange(1.0, 600.0)
        self.net_timeout.setDecimals(1)
        self.net_timeout.setSuffix(" s")
        self.net_retries = QSpinBox()
        self.net_retries.setRange(0, 10)
        network.addRow("HTTP proxy", self.proxy)
        network.addRow("Rate limit (0 = off)", self.rate_limit)
        network.addRow("Network timeout", self.net_timeout)
        network.addRow("Network retries", self.net_retries)
        self.body.addLayout(network)

        paths = QFormLayout()
        paths.setSpacing(10)
        self.db_path = QLineEdit()
        self.exports_dir = QLineEdit()
        self.plugins_dir = QLineEdit()
        self.logs_dir = QLineEdit()
        paths.addRow("Database path", self.db_path)
        paths.addRow("Exports directory", self.exports_dir)
        paths.addRow("Plugins directory", self.plugins_dir)
        paths.addRow("Logs directory", self.logs_dir)
        self.body.addLayout(paths)

        scanning = QFormLayout()
        scanning.setSpacing(10)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1.0, 600.0)
        self.timeout.setDecimals(1)
        self.timeout.setSuffix(" s")
        self.max_workers = QSpinBox()
        self.max_workers.setRange(1, 64)
        scanning.addRow("Default scan timeout", self.timeout)
        scanning.addRow("Max scan workers", self.max_workers)
        self.body.addLayout(scanning)

        caching = QFormLayout()
        caching.setSpacing(10)
        self.cache_enabled = QCheckBox("Enable response cache")
        self.cache_ttl = QDoubleSpinBox()
        self.cache_ttl.setRange(1.0, 86400.0)
        self.cache_ttl.setDecimals(1)
        self.cache_ttl.setSuffix(" s")
        self.cache_max = QSpinBox()
        self.cache_max.setRange(1, 100000)
        caching.addRow("Cache", self.cache_enabled)
        caching.addRow("Cache TTL", self.cache_ttl)
        caching.addRow("Cache max size", self.cache_max)
        self.body.addLayout(caching)

        logging_form = QFormLayout()
        logging_form.setSpacing(10)
        self.log_level = QComboBox()
        self.log_level.addItems(list(_LOG_LEVELS))
        self.log_file = QLineEdit()
        self.log_max_bytes = QSpinBox()
        self.log_max_bytes.setRange(1024, 1_000_000_000)
        self.log_max_bytes.setSingleStep(1024)
        self.log_backups = QSpinBox()
        self.log_backups.setRange(0, 100)
        logging_form.addRow("Log level", self.log_level)
        logging_form.addRow("Log file", self.log_file)
        logging_form.addRow("Log max bytes", self.log_max_bytes)
        logging_form.addRow("Log backup count", self.log_backups)
        self.body.addLayout(logging_form)

        self.body.addWidget(QLabel("Telemetry: always off (not configurable)."))

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
        self.cache_enabled.setChecked(bool(cfg.get("cache.enabled", True)))
        self.cache_ttl.setValue(float(cfg.get("cache.ttl", 300.0)))
        self.cache_max.setValue(int(cfg.get("cache.max_size", 1024)))
        self.proxy.setText(str(cfg.get("network.proxy", "")))
        self.rate_limit.setValue(float(cfg.get("network.rate_limit", 0.0)))
        self.net_timeout.setValue(float(cfg.get("network.timeout", 30.0)))
        self.net_retries.setValue(int(cfg.get("network.retries", 2)))
        theme = str(cfg.get("gui.theme", "dark")).lower()
        self.theme.setCurrentIndex(max(self.theme.findText(theme), 0))
        language = str(cfg.get("gui.language", "en")).lower()
        self.language.setCurrentIndex(max(self.language.findText(language), 0))
        level = str(cfg.get("logging.level", "INFO")).upper()
        index = self.log_level.findText(level)
        self.log_level.setCurrentIndex(max(index, 0))
        self.log_file.setText(str(cfg.get("logging.file", "")))
        self.log_max_bytes.setValue(int(cfg.get("logging.max_bytes", 1048576)))
        self.log_backups.setValue(int(cfg.get("logging.backup_count", 3)))
        self.set_status(f"editing {cfg.path}")

    def _save(self) -> None:
        cfg = self.ctx.config
        cfg.set("paths.db_path", self.db_path.text().strip())
        cfg.set("paths.exports_dir", self.exports_dir.text().strip())
        cfg.set("paths.plugins_dir", self.plugins_dir.text().strip())
        cfg.set("paths.logs_dir", self.logs_dir.text().strip())
        cfg.set("scan.default_timeout", float(self.timeout.value()))
        cfg.set("scan.max_workers", int(self.max_workers.value()))
        cfg.set("cache.enabled", bool(self.cache_enabled.isChecked()))
        cfg.set("cache.ttl", float(self.cache_ttl.value()))
        cfg.set("cache.max_size", int(self.cache_max.value()))
        cfg.set("network.proxy", self.proxy.text().strip())
        cfg.set("network.rate_limit", float(self.rate_limit.value()))
        cfg.set("network.timeout", float(self.net_timeout.value()))
        cfg.set("network.retries", int(self.net_retries.value()))
        cfg.set("gui.theme", self.theme.currentText())
        cfg.set("gui.language", self.language.currentText())
        cfg.set("app.telemetry", False)
        cfg.set("logging.level", self.log_level.currentText())
        cfg.set("logging.file", self.log_file.text().strip())
        cfg.set("logging.max_bytes", int(self.log_max_bytes.value()))
        cfg.set("logging.backup_count", int(self.log_backups.value()))
        try:
            cfg.save()
        except Exception as exc:
            self.set_status(f"could not save settings: {exc}")
            return
        self.set_status("settings saved")
