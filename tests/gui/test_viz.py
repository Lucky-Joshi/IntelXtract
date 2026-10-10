"""Phase 18 smoke tests (S18.6): widget builds offscreen + renders to bytes."""

from __future__ import annotations

from typing import Any

from gui.viz import (
    BarChartWidget,
    RelationGraphWidget,
    RiskPieWidget,
    TimelineView,
    TrendWidget,
    WorldMapWidget,
    export_png,
    export_svg,
    map_markers_from_result,
    module_bars,
    severity_bars,
    timeline_events,
    trend_points,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _payload() -> dict[str, Any]:
    return {
        "scan": {
            "uuid": "u1",
            "mode": "deep",
            "status": "completed",
            "started_at": 1_709_836_800.0,
            "finished_at": 1_709_836_860.0,
            "duration": 60.0,
        },
        "target": {"value": "example.com", "type": "domain"},
        "correlation": {
            "entities": [
                {"id": "domain:abc1", "kind": "domain", "value": "example.com"},
                {"id": "ip:e1475", "kind": "ip", "value": "93.184.216.34"},
                {"id": "org:aaaa", "kind": "organization", "value": "Acme Corp"},
                {"id": "email:cccc", "kind": "email", "value": "iana@iana.org"},
            ],
            "edges": [
                {
                    "source": "domain:abc1",
                    "target": "ip:e1475",
                    "type": "resolves_to",
                    "confidence": 1.0,
                },
                {
                    "source": "org:aaaa",
                    "target": "email:cccc",
                    "type": "same_email",
                    "confidence": 0.9,
                },
            ],
            "stats": {"entities": 4, "edges": 2},
        },
        "risk": {
            "target": "example.com",
            "score": 59.0,
            "rating": "high",
            "categories": {
                "TLS": {"score": 35.0, "rules": 1},
                "HEADERS": {"score": 18.0, "rules": 2},
                "DNS": {"score": 6.0, "rules": 1},
                "EXPOSURE": {"score": 0.0, "rules": 0},
            },
            "rules": [],
            "summary": [],
        },
        "findings": [
            {
                "module": "ssl",
                "title": "SSL: certificate expired",
                "severity": "high",
                "data": {"host": "example.com"},
            },
            {
                "module": "dns",
                "title": "DNS: no DMARC record",
                "severity": "low",
                "data": {},
            },
            {
                "module": "geo",
                "title": "Geo: IP location",
                "severity": "info",
                "data": {"country_code": "US"},
            },
            {
                "module": "geo",
                "title": "Geo: IP location",
                "severity": "info",
                "data": {"country_code": "US"},
            },
            {
                "module": "geo",
                "title": "Geo: IP location",
                "severity": "info",
                "data": {
                    "country_code": "DE",
                    "latitude": 52.52,
                    "longitude": 13.40,
                },
            },
            {
                "module": "news",
                "title": "News: timeline",
                "severity": "info",
                "data": {
                    "articles": [
                        {
                            "title": "Story A",
                            "published": "2024-03-01T08:00:00+00:00",
                            "url": "https://p.example/a",
                        },
                        {
                            "title": "Story A",
                            "published": "2024-03-01T08:00:00+00:00",
                            "url": "https://p.example/a",
                        },
                        {
                            "title": "Story B",
                            "published": "2024-03-02T08:00:00+00:00",
                            "url": "https://p.example/b",
                        },
                    ]
                },
            },
        ],
    }


def test_widgets_render_to_png_and_svg(qapp: Any) -> None:
    widgets = [
        RelationGraphWidget(),
        TimelineView(),
        RiskPieWidget(),
        BarChartWidget(),
        TrendWidget(),
        WorldMapWidget(),
    ]
    for widget in widgets:
        assert export_png(widget)[:8] == PNG_MAGIC
        svg = export_svg(widget)
        assert svg.startswith(b"<?xml") or b"<svg" in svg[:200]


def test_graph_render_is_deterministic(qapp: Any) -> None:
    widget = RelationGraphWidget()
    widget.set_correlation(_payload()["correlation"], target="example.com")
    assert export_png(widget) == export_png(widget)


def test_timeline_events_sort_and_dedupe() -> None:
    events = timeline_events(_payload())
    kinds = [item["kind"] for item in events]
    assert kinds == sorted(kinds)
    labels = [item["label"] for item in events if item["kind"] == "news"]
    assert labels == ["Story A", "Story B"]
    stamps = [item["ts"] for item in events]
    assert stamps == sorted(stamps)
    assert len(events) == 4  # 2 scans + 2 unique news articles


def test_bar_helpers() -> None:
    findings = _payload()["findings"]
    severity = severity_bars(findings)
    assert severity[0] == {"label": "critical", "value": 0, "color": "#c62828"}
    by_severity = {item["label"]: item["value"] for item in severity}
    assert by_severity["high"] == 1
    assert by_severity["low"] == 1
    assert by_severity["info"] == 4

    modules = module_bars(findings)
    by_module = {item["label"]: item["value"] for item in modules}
    assert by_module["geo"] == 3
    assert modules[0]["label"] == "geo"


def test_map_markers_group_by_country() -> None:
    markers = map_markers_from_result(_payload())
    assert {"country_code": "US", "count": 2} in markers
    of = {item["country_code"]: item for item in markers if "country_code" in item}
    assert of["US"]["count"] == 2
    assert "DE" not in of  # DE carried explicit lat/lon, so it is a point marker
    explicit = [item for item in markers if "lat" in item and "lon" in item]
    assert explicit == [{"lat": 52.52, "lon": 13.4, "count": 1}]


def test_trend_points_fall_back_to_duration() -> None:
    points = trend_points({"started_at": 1000.0, "duration": 5.0})
    assert points == [{"ts": 1000.0, "value": 5.0}]
    assert (
        trend_points({"score": 50.0, "started_at": 1000.0, "duration": 5.0})[0]["value"]
        == 50.0
    )
    assert trend_points({}) == []
    assert trend_points(None) == []


def test_export_png_writes_file(tmp_path: Any, qapp: Any) -> None:
    widget = BarChartWidget()
    widget.set_bars("S", [{"label": "a", "value": 2, "color": "#000000"}])
    target = tmp_path / "s18.png"
    data = export_png(widget, str(target))
    assert target.read_bytes() == data
    assert target.read_bytes()[:8] == PNG_MAGIC


def test_results_page_renders_visualization_tab(make_window: Any, gui_env: Any) -> None:
    results = make_window().page("results")
    results.show_result(_payload())

    assert results.graph_widget.correlation is not None
    assert len(results.timeline_view.events) == 4
    assert results.risk_pie._slices()
    assert results.severity_chart.bars
    assert results.module_chart.bars
    assert export_png(results.graph_widget)[:8] == PNG_MAGIC
    assert export_png(results.map_widget)[:8] == PNG_MAGIC
