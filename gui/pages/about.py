"""About page: version, license, environment, links."""

from __future__ import annotations

import platform
import sys
from typing import Any

import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QLabel

from core.constants import APP_NAME, VERSION
from gui.pages.base import Page

_REPO_URL = "https://github.com/Lucky-Joshi/IntelXtract"
_LICENSE = "GPL-3.0"


class AboutPage(Page):
    """Static information about the application."""

    page_id = "about"
    title = "About"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)

        lines = (
            f"{APP_NAME} {VERSION}",
            "",
            "AI-powered OSINT automation and intelligence platform.",
            "Public, authorized research only.",
            "",
            f"License: {_LICENSE}",
            f"Repository: {_REPO_URL}",
            "",
            f"Python {platform.python_version()} ({sys.executable})",
            f"Qt {qVersion()} (PySide6 {PySide6.__version__})",
            f"Platform: {platform.platform()}",
            f"Config: {ctx.config.path}",
            f"Database: {ctx.db_path}",
        )
        body = QLabel("\n".join(lines))
        body.setWordWrap(True)
        self.body.addWidget(body)

    def refresh(self) -> None:
        return None
