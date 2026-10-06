"""Qt theme built from ``docs/brand/BRAND.md`` tokens.

Dark theme is the default (BRAND.md). Every colour in the stylesheet comes
from the token tables there; keep the two in sync when branding changes.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

COLORS: dict[str, str] = {
    "bg": "#0B1220",
    "surface": "#111A2C",
    "surface_2": "#1A2438",
    "border": "#1E293B",
    "primary": "#3B82F6",
    "accent": "#22D3EE",
    "primary_hover": "#2563EB",
    "text": "#E2E8F0",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "shadow": "rgba(0, 0, 0, 0.45)",
}

FONT_UI = 'Inter, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
FONT_MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'

DARK_QSS = f"""
QMainWindow, QDialog {{
    background-color: {COLORS["bg"]};
    color: {COLORS["text"]};
    font-family: {FONT_UI};
    font-size: 14px;
}}
QWidget {{
    color: {COLORS["text"]};
}}
QFrame#sidebar {{
    background-color: {COLORS["surface"]};
    border-right: 1px solid {COLORS["border"]};
}}
QLabel#app-title {{
    font-size: 16px;
    font-weight: 600;
    color: {COLORS["accent"]};
    padding: 16px 12px 8px 12px;
}}
QLabel#title {{
    font-size: 20px;
    font-weight: 600;
    color: {COLORS["text"]};
    padding-bottom: 4px;
}}
QLabel#section {{
    font-size: 16px;
    font-weight: 600;
    color: {COLORS["text"]};
}}
QLabel#muted, QLabel#caption {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
}}
QLabel#banner {{
    background-color: {COLORS["warning"]};
    color: #111111;
    border-radius: 6px;
    padding: 8px 12px;
    font-weight: 500;
}}
QLabel#stat-value {{
    font-size: 22px;
    font-weight: 700;
    color: {COLORS["text"]};
}}
QLabel#stat-label {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
}}
QPushButton#nav-button {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 6px;
    color: {COLORS["text_secondary"]};
    text-align: left;
    padding: 8px 12px;
    font-size: 14px;
    margin: 2px 8px;
}}
QPushButton#nav-button:hover {{
    background-color: {COLORS["surface_2"]};
    color: {COLORS["text"]};
}}
QPushButton#nav-button:checked {{
    background-color: {COLORS["surface_2"]};
    border-left: 3px solid {COLORS["accent"]};
    color: {COLORS["accent"]};
    font-weight: 500;
}}
QPushButton#primary {{
    background-color: {COLORS["primary"]};
    color: #FFFFFF;
    border: 1px solid {COLORS["primary"]};
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 500;
}}
QPushButton#primary:hover {{
    background-color: {COLORS["primary_hover"]};
    border-color: {COLORS["primary_hover"]};
}}
QPushButton#primary:disabled {{
    background-color: {COLORS["surface_2"]};
    border-color: {COLORS["border"]};
    color: {COLORS["text_muted"]};
}}
QPushButton#secondary {{
    background-color: {COLORS["surface_2"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton#secondary:hover {{
    border-color: {COLORS["primary"]};
    color: {COLORS["accent"]};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {COLORS["surface_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    color: {COLORS["text"]};
    selection-background-color: {COLORS["primary"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {COLORS["primary"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["surface_2"]};
    selection-color: {COLORS["text"]};
}}
QCheckBox {{
    spacing: 8px;
    color: {COLORS["text"]};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    background-color: {COLORS["surface_2"]};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
}}
QGroupBox {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {COLORS["text_secondary"]};
}}
QTableWidget, QTableView {{
    background-color: {COLORS["surface"]};
    alternate-background-color: {COLORS["surface_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    gridline-color: {COLORS["border"]};
    selection-background-color: {COLORS["surface_2"]};
    selection-color: {COLORS["accent"]};
}}
QTableWidget::item {{
    padding: 6px 8px;
    border: none;
}}
QHeaderView::section {{
    background-color: {COLORS["surface_2"]};
    color: {COLORS["text_secondary"]};
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    padding: 8px 12px;
    font-weight: 500;
}}
QTabWidget::pane {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    background-color: {COLORS["surface"]};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {COLORS["surface"]};
    color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border"]};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    background-color: {COLORS["surface_2"]};
    color: {COLORS["accent"]};
    font-weight: 500;
}}
QProgressBar {{
    background-color: {COLORS["surface_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    text-align: center;
    color: {COLORS["text"]};
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {COLORS["primary"]};
    border-radius: 5px;
}}
QStatusBar {{
    background-color: {COLORS["surface"]};
    border-top: 1px solid {COLORS["border"]};
    color: {COLORS["text_secondary"]};
    font-size: 12px;
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background-color: {COLORS["bg"]};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {COLORS["surface_2"]};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QSplitter::handle {{
    background-color: {COLORS["border"]};
}}
"""


def apply_theme(app: QGuiApplication | QApplication) -> None:
    """Apply the dark Fusion theme to a running application."""
    if isinstance(app, QApplication):
        app.setStyle("Fusion")
        app.setStyleSheet(DARK_QSS)
