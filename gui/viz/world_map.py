"""Phase 18 (S18.4): coarse world map of geolocated targets.

Pure, tile-less and offline: an equirectangular projection renders the
committed coarse country polygons, then dots each country's centroid per
``Geo: IP location`` findings (or explicit lat/lon when available).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from gui.viz.base import VizWidget, _title_text, draw_empty

_WORLD_FILE = Path(__file__).parent / "data" / "world_coarse.json"


def _load_countries() -> dict[str, dict[str, Any]]:
    if not _WORLD_FILE.exists():
        return {}
    import json

    with _WORLD_FILE.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    countries: dict[str, dict[str, Any]] = {}
    for row in rows:
        countries[str(row["iso_a2"])] = row
    return countries


_WORLD = _load_countries()


def _countries() -> dict[str, dict[str, Any]]:
    return _WORLD


def map_markers_from_result(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Count geolocated targets per country; include lat/lon when provided."""
    counts: Counter = Counter()
    explicit: dict[str, dict[str, Any]] = {}
    for finding in payload.get("findings") or []:
        if not isinstance(finding, dict) or finding.get("module") != "geo":
            continue
        data = finding.get("data")
        if not isinstance(data, dict):
            continue
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            key = f"{float(latitude):.2f},{float(longitude):.2f}"
            explicit[key] = {
                "lat": float(latitude),
                "lon": float(longitude),
                "count": int(explicit.get(key, {}).get("count", 0)) + 1,
            }
            continue
        code = data.get("country_code")
        if isinstance(code, str) and code:
            counts[code] += 1
    markers = [
        {"country_code": code, "count": int(count)} for code, count in counts.items()
    ]
    markers.extend(
        {
            "lat": item["lat"],
            "lon": item["lon"],
            "count": int(item["count"]),
        }
        for item in explicit.values()
    )
    markers.sort(
        key=lambda item: (
            item.get("country_code", ""),
            item.get("lat", 0.0),
            item.get("lon", 0.0),
        )
    )
    return markers


class WorldMapWidget(VizWidget):
    """Coarse, offline world map with geolocation markers."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.markers: list[dict[str, Any]] = []

    def set_markers(self, markers: list[dict[str, Any]]) -> None:
        self.markers = list(markers)
        self.update()

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        body = _title_text(painter, rect, "Target geography")
        markers = self.markers
        if not markers:
            draw_empty(painter, body, "No geolocated targets for this result.")
            return

        painter.setBrush(QColor("#d9e6f2"))
        painter.setPen(QPen(QColor("#d9e6f2")))
        painter.drawRect(body)

        self._draw_graticule(painter, body)
        self._draw_land(painter, body)
        self._draw_markers(painter, body)

    def _project(self, lon: float, lat: float, body: QRectF) -> QPointF:
        margin = self.margin
        world_lon = 360.0
        x = (
            body.x()
            + (lon + 180.0) / world_lon * (body.width() - 2.0 * margin)
            + margin
        )
        y = body.y() + (90.0 - lat) / 180.0 * (body.height() - 2.0 * margin) + margin
        return QPointF(x, y)

    def _draw_graticule(self, painter: QPainter, body: QRectF) -> None:
        painter.setPen(QPen(QColor("#bfd6e8")))
        for lon in range(-150, 181, 30):
            painter.drawLine(
                self._project(lon, -90.0, body), self._project(lon, 90.0, body)
            )
        for lat in range(-60, 61, 30):
            painter.drawLine(
                self._project(-180.0, lat, body), self._project(180.0, lat, body)
            )

    def _draw_land(self, painter: QPainter, body: QRectF) -> None:
        painter.setPen(QPen(QColor("#b7c4ad")))
        painter.setBrush(QColor("#dbe5c9"))
        for row in _countries().values():
            for ring in row.get("rings", []):
                path = QPainterPath(self._project(ring[0][0], ring[0][1], body))
                for lon, lat in ring[1:]:
                    path.lineTo(self._project(lon, lat, body))
                painter.drawPath(path)

    def _draw_markers(self, painter: QPainter, body: QRectF) -> None:
        for marker in self.markers:
            point = self._marker_point(marker, body)
            if point is None:
                continue
            count = int(marker.get("count") or 1)
            radius = 3.0 + 2.5 * min(count, 6)
            painter.setPen(QPen(QColor("#c62828").darker(110)))
            painter.setBrush(QColor("#ef5350"))
            painter.drawEllipse(point, radius, radius)

    def _marker_point(self, marker: dict[str, Any], body: QRectF) -> QPointF | None:
        lat = marker.get("lat")
        lon = marker.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return self._project(float(lon), float(lat), body)
        code = marker.get("country_code")
        row = _countries().get(str(code))
        centroid = row.get("centroid") if row else None
        if isinstance(centroid, dict):
            return self._project(float(centroid["lon"]), float(centroid["lat"]), body)
        return None


__all__ = ["WorldMapWidget", "map_markers_from_result"]
