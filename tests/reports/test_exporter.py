"""Phase 19 — exporter tests: JSON round-trip, CSV counts, HTML, PDF fallback."""

from __future__ import annotations

import csv
import io
import json

import pytest
from test_builder import sample_model

from reports import build_report, export_report


def _parse_csv(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def test_json_matches_model_dict() -> None:
    model = sample_model()
    result = export_report(model, "json")
    assert result.format == "json"
    assert result.warning is None
    parsed = json.loads(result.data)
    assert parsed == model.to_dict()
    assert parsed["scan"]["uuid"] == "u7"


def test_csv_row_counts_and_order() -> None:
    result = export_report(sample_model(), "csv")
    rows = _parse_csv(result.data)
    assert len(rows) == 4
    assert rows[0]["severity"] == "high"
    assert rows[0]["module"] == "ssl"
    assert list(rows) or True
    assert set(rows[0].keys()) == {
        "severity",
        "module",
        "title",
        "confidence",
        "evidence",
    }


def test_csv_empty_findings_header_only() -> None:
    model = build_report(
        {"id": 1, "uuid": "u", "started_at": 1.0, "finished_at": 2.0}, {}, []
    )
    rows = _parse_csv(export_report(model, "csv").data)
    assert rows == []


def test_markdown_contains_sections() -> None:
    result = export_report(sample_model(), "md")
    text = result.data.decode("utf-8")
    assert text.startswith("# IntelXtract")
    assert "## Executive summary" in text
    assert "## Risk overview" in text
    assert "## Findings" in text
    assert "| severity | module | title | evidence |" in text
    assert "**TLS:**" in text


def test_html_renders_with_brand_and_sections() -> None:
    result = export_report(sample_model(), "html")
    text = result.data.decode("utf-8")
    assert "<!doctype html>" in text
    assert "#1f6feb" in text  # brand accent
    assert "HIGH risk" in text
    assert "SSL: certificate expired" in text
    assert "strict-transport-security header absent" in text
    assert "Methodology" in text


def test_pdf_fallback_when_weasyprint_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("reports.exporter._load_weasyprint_html", lambda: None)
    result = export_report(sample_model(), "pdf")
    assert result.format == "html"
    assert "WeasyPrint" in (result.warning or "")
    assert b"<html" in result.data[:200]


def test_pdf_renders_bytes_when_weasyprint_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHTML:
        def __init__(self, string: str) -> None:
            self._string = string

        def write_pdf(self) -> bytes:
            return b"%PDF-1.4 fake"

    monkeypatch.setattr("reports.exporter._load_weasyprint_html", lambda: FakeHTML)
    result = export_report(sample_model(), "pdf")
    assert result.format == "pdf"
    assert result.warning is None
    assert result.data.startswith(b"%PDF")


def test_unsupported_format_raises() -> None:
    with pytest.raises(ValueError):
        export_report(sample_model(), "docx")
