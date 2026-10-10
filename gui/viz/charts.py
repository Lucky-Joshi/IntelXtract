"""Phase 18 (S18.3): paint-based charts — risk pie, module/severity bars, trend.

No third-party charting library is required: each widget paints itself with
``QPainter`` and exports through :mod:`gui.viz.base`, keeping the report
embeds faithful to what the GUI shows.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from gui.viz.base import VizWidget, _grid_pen, _title_text, draw_empty

SEVERITY_COLORS = {
    "critical": "#c62828",
    "high": "#ef6c00",
    "medium": "#f9a825",
    "low": "#42a5f5",
    "info": "#9e9e9e",
}
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

RISK_CATEGORY_COLORS = {
    "TLS": "#8b5cf6",
    "HEADERS": "#3b82f6",
    "DNS": "#10b981",
    "EXPOSURE": "#f59e0b",
}

MODULE_PALETTE = (
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#ec4899",
    "#8b5cf6",
    "#06b6d4",
    "#14b8a6",
    "#f97316",
    "#64748b",
    "#94a3b8",
)


def severity_bars(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bar data: finding count per severity, documented order."""
    counts = Counter(str(finding.get("severity") or "info") for finding in findings)
    bars: list[dict[str, Any]] = []
    for level in SEVERITY_ORDER:
        value = int(counts.get(level, 0))
        bars.append({"label": level, "value": value, "color": SEVERITY_COLORS[level]})
    return bars


def module_bars(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bar data: finding count per module, highest first, capped for space."""
    counts = Counter(str(finding.get("module") or "unknown") for finding in findings)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    bars: list[dict[str, Any]] = []
    for index, (module, value) in enumerate(ranked[:10]):
        bars.append(
            {
                "label": str(module),
                "value": int(value),
                "color": MODULE_PALETTE[index % len(MODULE_PALETTE)],
            }
        )
    return bars


def trend_points(scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """One trend point from a scan row (duration; risk score if available)."""
    if not scan:
        return []
    started = scan.get("started_at")
    if not isinstance(started, (int, float)):
        return []
    value = scan.get("score")
    if not isinstance(value, (int, float)):
        value = scan.get("duration")
    if not isinstance(value, (int, float)):
        return []
    return [{"ts": float(started), "value": float(value)}]


class RiskPieWidget(VizWidget):
    """Pie chart of the Phase 17 risk sub-scores per category."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.risk: dict[str, Any] | None = None

    def set_risk(self, risk: dict[str, Any] | None) -> None:
        self.risk = risk
        self.update()

    def _slices(self) -> list[dict[str, Any]]:
        categories = (self.risk or {}).get("categories")
        if not isinstance(categories, dict):
            return []
        slices = []
        for name, meta in categories.items():
            if not isinstance(meta, dict):
                continue
            score = float(meta.get("score") or 0.0)
            if score > 0.0:
                slices.append(
                    {
                        "label": str(name),
                        "value": score,
                        "color": RISK_CATEGORY_COLORS.get(str(name), "#9aa0a6"),
                    }
                )
        return slices

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        body = _title_text(painter, rect, "Risk distribution")
        slices = self._slices()
        if not slices:
            draw_empty(painter, body, "No risk categories scored for this result.")
            return

        total = sum(float(item["value"]) for item in slices)
        side = min(body.width() - 150.0, body.height())
        center = QPointF(body.x() + side / 2.0, body.y() + side / 2.0)
        radius = side / 2.0 - 8.0

        start_angle = 90.0 * 16.0
        for item in slices:
            fraction = float(item["value"]) / total
            span = -fraction * 360.0 * 16.0
            painter.setPen(QPen(QColor(item["color"]).darker(110)))
            painter.setBrush(QColor(item["color"]))
            painter.drawPie(
                QRectF(
                    center.x() - radius, center.y() - radius, radius * 2.0, radius * 2.0
                ),
                int(start_angle),
                int(span),
            )
            start_angle += span

        legend_x = body.right() - 138.0
        legend_y = body.top() + 4.0
        painter.setPen(QColor("#3c4043"))
        for item in slices:
            painter.setBrush(QColor(item["color"]))
            painter.setPen(QPen(QColor(item["color"])))
            painter.drawRect(QRectF(legend_x, legend_y, 10.0, 10.0))
            percent = float(item["value"]) / total * 100.0
            painter.setPen(QColor("#202124"))
            painter.drawText(
                QRectF(legend_x + 16.0, legend_y - 2.0, 120.0, 18.0),
                int(Qt.AlignmentFlag.AlignLeft),
                f"{item['label']}  {percent:.0f}%",
            )
            legend_y += 20.0


class BarChartWidget(VizWidget):
    """Vertical bar chart for a normalized ``bars`` list."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.title = "Bar chart"
        self.bars: list[dict[str, Any]] = []

    def set_bars(self, title: str, bars: list[dict[str, Any]]) -> None:
        self.title = title
        self.bars = list(bars)
        self.update()

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        body = _title_text(painter, rect, self.title)
        bars = self.bars
        if not bars or all(int(item.get("value") or 0) == 0 for item in bars):
            draw_empty(painter, body, "No bars to plot.")
            return

        max_value = max(float(item.get("value") or 0.0) for item in bars)
        safe_max = max_value if max_value > 0.0 else 1.0
        axis_y = body.bottom() - 26.0
        slot = body.width() / len(bars)
        bar_width = slot * 0.62

        painter.setPen(_grid_pen())
        painter.drawLine(QLineF(body.left(), axis_y, body.right(), axis_y))
        painter.setPen(QColor("#5f6368"))
        for mark in (0.25, 0.5, 0.75, 1.0):
            y = axis_y - mark * (body.height() - 34.0)
            painter.drawLine(QLineF(body.left(), y, body.right(), y))

        for index, item in enumerate(bars):
            value = float(item.get("value") or 0.0)
            x = body.left() + index * slot + (slot - bar_width) / 2.0
            height = (value / safe_max) * (body.height() - 40.0)
            painter.setPen(QPen(QColor(item.get("color", "#9aa0a6"))))
            painter.setBrush(QColor(item.get("color", "#9aa0a6")))
            painter.drawRect(QRectF(x, axis_y - height, bar_width, height))
            painter.setPen(QColor("#202124"))
            painter.drawText(
                QRectF(x - 12.0, axis_y - height - 18.0, bar_width + 24.0, 16.0),
                int(Qt.AlignmentFlag.AlignCenter),
                f"{value:.0f}",
            )
            label = str(item.get("label", ""))
            if len(label) > 9:
                label = label[:8] + "…"
            painter.drawText(
                QRectF(x - 12.0, axis_y + 4.0, bar_width + 24.0, 18.0),
                int(Qt.AlignmentFlag.AlignCenter),
                label,
            )


class TrendWidget(VizWidget):
    """Line chart of scan statistics (duration or risk score) over time."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.title = "Scan trend"
        self.points: list[dict[str, Any]] = []

    def set_points(self, title: str, points: list[dict[str, Any]]) -> None:
        self.title = title
        self.points = list(points)
        self.update()

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        body = _title_text(painter, rect, self.title)
        points = sorted(self.points, key=lambda item: float(item.get("ts") or 0.0))
        if len(points) < 1:
            draw_empty(painter, body, "No scan history to plot.")
            return

        ts_values = [float(item["ts"]) for item in points]
        value_values = [float(item["value"]) for item in points]
        min_ts, max_ts = min(ts_values), max(ts_values)
        max_value = max(value_values)
        if max_ts - min_ts < 1.0:
            max_ts = min_ts + 1.0
        safe_max = max_value if max_value > 0.0 else 1.0

        axis_y = body.bottom() - 26.0
        painter.setPen(_grid_pen())
        painter.drawLine(QLineF(body.left(), axis_y, body.right(), axis_y))

        def map_position(index: int) -> QPointF:
            x = (
                body.left()
                + (ts_values[index] - min_ts) / (max_ts - min_ts) * body.width()
            )
            y = axis_y - (value_values[index] / safe_max) * (body.height() - 40.0)
            return QPointF(x, y)

        painter.setPen(QPen(QColor("#3b82f6")))
        for index in range(len(points) - 1):
            painter.drawLine(map_position(index), map_position(index + 1))
        painter.setBrush(QColor("#3b82f6"))
        painter.setPen(QPen(QColor("#3b82f6").darker(120)))
        for index in range(len(points)):
            position = map_position(index)
            painter.drawEllipse(position, 3.0, 3.0)
            painter.setPen(QColor("#3c4043"))
            painter.drawText(
                QRectF(position.x() - 30.0, position.y() - 20.0, 60.0, 16.0),
                int(Qt.AlignmentFlag.AlignCenter),
                f"{value_values[index]:.0f}",
            )


__all__ = [
    "BarChartWidget",
    "RiskPieWidget",
    "TrendWidget",
    "module_bars",
    "severity_bars",
    "trend_points",
]
