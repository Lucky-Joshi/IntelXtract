"""Phase 18 (S18.1): interactive-style relationship graph for a scan.

``RelationGraphWidget`` lays entities out with NetworkX's deterministic
spring layout, draws every correlation edge colored by type, and renders the
scene to the screen or to exported PNG/SVG via :mod:`gui.viz.base`.
"""

from __future__ import annotations

import math
import random as _random
from typing import Any

import networkx as nx  # type: ignore[import-untyped]
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from gui.viz.base import VizWidget, _title_text, draw_empty

KIND_COLORS = {
    "domain": "#3b82f6",
    "ip": "#10b981",
    "email": "#f59e0b",
    "organization": "#8b5cf6",
    "certificate": "#ec4899",
    "username": "#06b6d4",
    "social_profile": "#06b6d4",
    "technology": "#14b8a6",
    "phone": "#64748b",
    "document": "#94a3b8",
}

EDGE_COLORS = {
    "resolves_to": "#10b981",
    "registered_by": "#8b5cf6",
    "issued_to": "#ec4899",
    "same_email": "#f59e0b",
    "part_of": "#22d3ee",
    "mentions": "#64748b",
    "profile": "#06b6d4",
    "uses": "#14b8a6",
}

LABELED_KINDS = {"domain", "ip", "email", "organization", "certificate"}


class RelationGraphWidget(VizWidget):
    """Entity graph built from a Phase 16 correlation payload."""

    layout_seed = 7

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.correlation: dict[str, Any] | None = None
        self.target: str | None = None

    def set_correlation(
        self, correlation: dict[str, Any] | None, *, target: str | None = None
    ) -> None:
        self.correlation = correlation
        self.target = target
        self.update()

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        body = _title_text(painter, rect, "Relationship graph")
        corr = self.correlation
        if not corr or not corr.get("entities"):
            draw_empty(painter, body, "No correlation graph for this result.")
            return

        graph = self._build_graph(corr)
        positions = self._positions(graph, body)

        for source, target, data in graph.edges(data=True):
            start = positions[source]
            end = positions[target]
            edge_type = str(data.get("type", "mentions"))
            pen = QPen(QColor(EDGE_COLORS.get(edge_type, "#9aa0a6")))
            pen.setWidthF(1.4)
            painter.setPen(pen)
            painter.drawLine(start, end)

        degrees = dict(graph.degree())
        for node_id, position in positions.items():
            kind = str(graph.nodes[node_id].get("kind", ""))
            value = graph.nodes[node_id].get("value", "")
            color = QColor(KIND_COLORS.get(kind, "#9aa0a6"))
            radius = min(6.0 + degrees[node_id] * 1.1, 13.0)
            is_target = kind == "domain" and value == self.target
            painter.setPen(QPen(color.darker(120)))
            painter.setBrush(color)
            painter.drawEllipse(position, radius, radius)
            if is_target:
                ring = QPen(QColor("#f59e0b"))
                ring.setWidthF(2.2)
                painter.setPen(ring)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(position, radius + 3.5, radius + 3.5)
            if kind in LABELED_KINDS and value:
                self._draw_label(painter, position, str(value), radius + 5.0)

    def _build_graph(self, corr: dict[str, Any]) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        for entity in corr.get("entities", []):
            if not isinstance(entity, dict):
                continue
            graph.add_node(
                entity.get("id"),
                kind=entity.get("kind", ""),
                value=entity.get("value", ""),
            )
        for edge in corr.get("edges", []):
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source in graph and target in graph:
                graph.add_edge(source, target, type=edge.get("type", "mentions"))
        return graph

    def _positions(self, graph: nx.MultiDiGraph, body: QRectF) -> dict[Any, QPointF]:
        margin = self.margin
        layout = self._force_layout(graph)
        positions: dict[Any, QPointF] = {}
        for node, (x, y) in layout.items():
            px = body.x() + margin + x * (body.width() - 2.0 * margin)
            py = body.y() + margin + y * (body.height() - 2.0 * margin)
            positions[node] = QPointF(px, py)
        return positions

    def _force_layout(
        self, graph: nx.MultiDiGraph, *, seed: int = 7, iterations: int = 120
    ) -> dict[Any, tuple[float, float]]:
        """Deterministic, dependency-free Fruchterman-Reingold layout.

        Avoids ``networkx.spring_layout`` (which needs numpy) so exports stay
        byte-stable in any environment.
        """
        nodes = list(graph.nodes())
        if len(nodes) < 2:
            return {node: (0.5, 0.5) for node in nodes}
        rng = _random.Random(seed)  # noqa: S311 (layout-only RNG)
        position: dict[Any, list[float]] = {
            node: [rng.random(), rng.random()] for node in nodes
        }
        node_count = len(nodes)
        spring = math.sqrt(1.0 / node_count)
        edges = [
            (source, target) for source, target in graph.edges() if source != target
        ]
        for step in range(iterations):
            displacement: dict[Any, list[float]] = {node: [0.0, 0.0] for node in nodes}
            for left in range(node_count):
                for right in range(left + 1, node_count):
                    a, b = nodes[left], nodes[right]
                    dx = position[a][0] - position[b][0]
                    dy = position[a][1] - position[b][1]
                    dist = math.hypot(dx, dy) or 1e-9
                    force = spring * spring / dist
                    fx, fy = dx / dist * force, dy / dist * force
                    displacement[a][0] += fx
                    displacement[a][1] += fy
                    displacement[b][0] -= fx
                    displacement[b][1] -= fy
            for a, b in edges:
                dx = position[a][0] - position[b][0]
                dy = position[a][1] - position[b][1]
                dist = math.hypot(dx, dy) or 1e-9
                force = dist * dist / spring
                fx, fy = dx / dist * force, dy / dist * force
                displacement[a][0] -= fx
                displacement[a][1] -= fy
                displacement[b][0] += fx
                displacement[b][1] += fy
            temperature = max(0.03, 0.1 * (1.0 - step / iterations))
            for node in nodes:
                length = math.hypot(displacement[node][0], displacement[node][1])
                if length < 1e-9:
                    continue
                step_size = min(length, temperature)
                position[node][0] += displacement[node][0] / length * step_size
                position[node][1] += displacement[node][1] / length * step_size
                position[node][0] = min(1.0, max(0.0, position[node][0]))
                position[node][1] = min(1.0, max(0.0, position[node][1]))
        return {node: (point[0], point[1]) for node, point in position.items()}

    def _draw_label(
        self, painter: QPainter, position: QPointF, text: str, offset: float
    ) -> None:
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor("#3c4043"))
        shown = text if len(text) <= 22 else f"{text[:19]}…"
        painter.drawText(
            QRectF(position.x() + offset, position.y() - offset, 160.0, 20.0),
            int(Qt.AlignmentFlag.AlignLeft),
            shown,
        )


__all__ = ["KIND_COLORS", "RelationGraphWidget"]
