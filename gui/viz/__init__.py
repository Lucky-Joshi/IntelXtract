"""Phase 18 — Visualization widgets and export helpers.

Every widget renders off-screen to PNG/SVG through ``VizWidget``, so the same
code drives the GUI and report embedding.
"""

from __future__ import annotations

from gui.viz.base import VizWidget, export_png, export_svg
from gui.viz.charts import (
    BarChartWidget,
    RiskPieWidget,
    TrendWidget,
    module_bars,
    severity_bars,
    trend_points,
)
from gui.viz.graph_widget import RelationGraphWidget
from gui.viz.timeline import TimelineView, timeline_events
from gui.viz.world_map import WorldMapWidget, map_markers_from_result

__all__ = [
    "BarChartWidget",
    "RelationGraphWidget",
    "RiskPieWidget",
    "TimelineView",
    "TrendWidget",
    "VizWidget",
    "WorldMapWidget",
    "export_png",
    "export_svg",
    "map_markers_from_result",
    "module_bars",
    "severity_bars",
    "timeline_events",
    "trend_points",
]
