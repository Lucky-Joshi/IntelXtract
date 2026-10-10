"""Phase 18 (S18.2): scan + news timeline on a shared time axis.

``TimelineView`` draws dated events (scan start/finish, news articles) across
horizontal lanes. :func:`timeline_events` normalizes a results payload into
the event list the widget consumes.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from gui.viz.base import VizWidget, _grid_pen, _title_text, draw_empty

KIND_COLORS = {
    "scan": "#3b82f6",
    "news": "#f59e0b",
}
LANES = ("scan", "news")
LANE_LABELS = {"scan": "Screens/scans", "news": "News mentions"}


def _to_epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = _dt.datetime.fromisoformat(normalized)
            return parsed.timestamp()
        except ValueError:
            return None
    return None


def timeline_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a deterministic, time-sorted event list from a results payload."""
    events: list[dict[str, Any]] = []
    scan = payload.get("scan") or {}
    started = _to_epoch(scan.get("started_at"))
    finished = _to_epoch(scan.get("finished_at"))
    if started is not None:
        events.append(
            {
                "ts": started,
                "kind": "scan",
                "label": f"scan started ({scan.get('mode', 'unknown')})",
            }
        )
    if finished is not None:
        events.append({"ts": finished, "kind": "scan", "label": "scan finished"})

    seen: set[tuple[str, float, str]] = set()
    findings = payload.get("findings") or []
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("module") != "news":
            continue
        data = finding.get("data")
        if not isinstance(data, dict):
            continue
        for article in data.get("articles") or []:
            if not isinstance(article, dict):
                continue
            published = _to_epoch(article.get("published"))
            if published is None:
                continue
            title = str(article.get("title") or "news item")
            key = ("news", published, title)
            if key in seen:
                continue
            seen.add(key)
            events.append({"ts": published, "kind": "news", "label": title})

    events.sort(key=lambda item: (item["ts"], item["kind"], item["label"]))
    return events


class TimelineView(VizWidget):
    """Horizontal timeline with a lane per event kind."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.events: list[dict[str, Any]] = []

    def set_events(self, events: list[dict[str, Any]]) -> None:
        self.events = list(events)
        self.update()

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        body = _title_text(painter, rect, "Timeline")
        if not self.events:
            draw_empty(painter, body, "No dated events for this result.")
            return

        min_ts = min(float(item["ts"]) for item in self.events)
        max_ts = max(float(item["ts"]) for item in self.events)
        if max_ts - min_ts < 1.0:
            max_ts = min_ts + 1.0
        span = max_ts - min_ts

        axis_y = body.bottom() - 24.0
        painter.setPen(_grid_pen())
        painter.drawLine(QLineF(body.left(), axis_y, body.right(), axis_y))
        self._draw_ticks(painter, body, min_ts, span, axis_y)

        lane_height = 34.0
        for lane_index, kind in enumerate(LANES):
            lane_y = body.top() + 18.0 + lane_index * lane_height
            painter.setPen(QColor("#5f6368"))
            painter.drawText(
                QRectF(body.left(), lane_y - 6.0, 130.0, 20.0),
                int(Qt.AlignmentFlag.AlignLeft),
                LANE_LABELS[kind],
            )
            for item in self.events:
                if item.get("kind") != kind:
                    continue
                x = body.left() + (float(item["ts"]) - min_ts) / span * body.width()
                y = lane_y + lane_height / 2.0
                painter.setPen(QPen(QColor(KIND_COLORS[kind])))
                painter.setBrush(QColor(KIND_COLORS[kind]))
                painter.drawEllipse(QPointF(x, y), 4.0, 4.0)
                painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_ticks(
        self, painter: QPainter, body: QRectF, min_ts: float, span: float, axis_y: float
    ) -> None:
        painter.setPen(QColor("#3c4043"))
        ticks = 6
        for index in range(ticks):
            fraction = index / (ticks - 1)
            x = body.left() + fraction * body.width()
            value = min_ts + fraction * span
            stamp = _dt.datetime.fromtimestamp(value).strftime("%Y-%m-%d")
            painter.drawText(
                QRectF(x - 40.0, axis_y + 6.0, 84.0, 18.0),
                int(Qt.AlignmentFlag.AlignCenter),
                stamp,
            )


__all__ = ["TimelineView", "timeline_events"]
