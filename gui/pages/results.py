"""Results page: per-module runs, findings, correlation stub."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.db_sync import recent_scans
from gui.pages.base import Page
from gui.viz import (
    BarChartWidget,
    RelationGraphWidget,
    RiskPieWidget,
    TimelineView,
    TrendWidget,
    WorldMapWidget,
    map_markers_from_result,
    module_bars,
    severity_bars,
    timeline_events,
    trend_points,
)


def normalize_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept engine dicts and persisted-history dicts alike."""
    if "scan" in payload:
        return payload
    return {
        "scan": {
            "id": None,
            "uuid": payload.get("scan_id"),
            "mode": payload.get("mode"),
            "status": payload.get("status"),
            "started_at": payload.get("started_at"),
            "finished_at": payload.get("finished_at"),
            "duration": payload.get("duration"),
            "error": payload.get("error"),
            "runs": payload.get("runs", []),
        },
        "target": {
            "value": payload.get("target"),
            "type": payload.get("target_type"),
        },
        "findings": payload.get("findings", []),
        "correlation": payload.get("correlation"),
        "risk": payload.get("risk"),
    }


class ResultsPage(Page):
    """Tabbed view of the most recent (or selected) scan result."""

    page_id = "results"
    title = "Results"

    def __init__(self, ctx: Any, parent: Any = None) -> None:
        super().__init__(ctx, parent)
        self._payload: dict[str, Any] | None = None

        self.target_label = QLabel("no scan selected")
        self.target_label.setObjectName("section")
        self.body.addWidget(self.target_label)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("muted")
        self.body.addWidget(self.meta_label)

        self.tabs = QTabWidget()
        self.runs_table = QTableWidget(0, 4)
        self.runs_table.setHorizontalHeaderLabels(
            ["module", "status", "duration (s)", "error"]
        )
        self.runs_table.verticalHeader().setVisible(False)
        self.runs_table.setAlternatingRowColors(True)
        self.runs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings_table = QTableWidget(0, 4)
        self.findings_table.setHorizontalHeaderLabels(
            ["module", "severity", "confidence", "data"]
        )
        self.findings_table.verticalHeader().setVisible(False)
        self.findings_table.setAlternatingRowColors(True)
        self.findings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.correlation = QLabel(
            "Correlation view arrives in Phase 20. Findings from every module "
            "will be clustered here."
        )
        self.correlation.setObjectName("muted")
        self.correlation.setWordWrap(True)
        self.tabs.addTab(self.runs_table, "Modules")
        self.tabs.addTab(self.findings_table, "Findings")
        self.tabs.addTab(self.correlation, "Correlation")
        self.tabs.addTab(self._build_visualization_tab(), "Visualization")
        self.body.addWidget(self.tabs, stretch=1)

        self.ctx.bridge.scan_finished.connect(
            self.show_result, Qt.ConnectionType.QueuedConnection
        )

    def refresh(self) -> None:
        return None

    def _build_visualization_tab(self) -> QWidget:
        """Phase 18: graph + timeline + charts + maps for the loaded result."""
        self.graph_widget = RelationGraphWidget()
        self.timeline_view = TimelineView()
        self.risk_pie = RiskPieWidget()
        self.severity_chart = BarChartWidget()
        self.module_chart = BarChartWidget()
        self.trend_chart = TrendWidget()
        self.map_widget = WorldMapWidget()

        viz_tabs = QTabWidget()
        viz_tabs.addTab(self.graph_widget, "Graph")
        viz_tabs.addTab(self.timeline_view, "Timeline")
        viz_tabs.addTab(self._build_charts_tab(), "Charts")
        viz_tabs.addTab(self.map_widget, "Map")
        return viz_tabs

    def _build_charts_tab(self) -> QWidget:
        charts_host = QWidget()
        charts_layout = QVBoxLayout(charts_host)
        top_row = QHBoxLayout()
        self.severity_chart.setMinimumWidth(220)
        self.module_chart.setMinimumWidth(280)
        self.risk_pie.setMinimumWidth(200)
        top_row.addWidget(self.risk_pie, 2)
        top_row.addWidget(self.severity_chart, 3)
        top_row.addWidget(self.module_chart, 3)
        charts_layout.addLayout(top_row, 3)
        charts_layout.addWidget(self.trend_chart, 2)
        return charts_host

    def _render_visualizations(self) -> None:
        payload = self._payload or {}
        target = str((payload.get("target") or {}).get("value") or "")
        self.graph_widget.set_correlation(payload.get("correlation"), target=target)
        self.timeline_view.set_events(timeline_events(payload))
        self.risk_pie.set_risk(payload.get("risk"))

        findings = payload.get("findings") or []
        self.severity_chart.set_bars("Findings by severity", severity_bars(findings))
        self.module_chart.set_bars("Findings by module", module_bars(findings))

        history: list[dict[str, Any]] = []
        try:
            history = recent_scans(self.ctx.db_path, limit=12)
        except Exception:
            history = []
        scan = payload.get("scan") or {}
        points = trend_points(scan)
        for row in history:
            row_points = trend_points(row) or []
            if row_points:
                points.append(row_points[0])
        self.trend_chart.set_points("Scan trend (duration / risk)", points)
        self.map_widget.set_markers(map_markers_from_result(payload))

    def show_result(self, payload: dict[str, Any]) -> None:
        """Render a scan result payload (engine or history shape)."""
        data = normalize_result(payload)
        self._payload = data
        scan = data.get("scan", {})
        target = data.get("target") or {}
        self.target_label.setText(str(target.get("value") or scan.get("uuid") or "—"))
        self.meta_label.setText(
            f"type={target.get('type', '—')}  mode={scan.get('mode', '—')}  "
            f"status={scan.get('status', '—')}  duration={scan.get('duration', 0)}  "
            f"uuid={scan.get('uuid', '—')}"
        )
        runs = scan.get("runs") or []
        self.runs_table.setRowCount(len(runs))
        for row_idx, run in enumerate(runs):
            if not isinstance(run, dict):
                continue
            error = run.get("error") or ""
            if isinstance(error, str) and len(error) > 120:
                error = error[:117] + "…"
            values = (
                str(run.get("module", "")),
                str(run.get("status", "")),
                str(run.get("duration", "")),
                error,
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.runs_table.setItem(row_idx, col, item)

        findings = data.get("findings") or []
        self.findings_table.setRowCount(len(findings))
        for row_idx, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            raw_data = finding.get("data")
            preview = (
                json.dumps(raw_data, ensure_ascii=False, default=str)
                if raw_data is not None
                else ""
            )
            if len(preview) > 100:
                preview = preview[:97] + "…"
            values = (
                str(finding.get("module", "")),
                str(finding.get("severity") or "—"),
                str(finding.get("confidence") or "—"),
                preview,
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.findings_table.setItem(row_idx, col, item)
        self._render_visualizations()
        self.set_status("result loaded")
