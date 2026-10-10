"""Metadata module collector tests (Phase 14, S14.1-S14.4)."""

from __future__ import annotations

from pathlib import Path

from core.engine import ModuleContext
from fakes import make_module_config, make_module_context
from modules.metadata.collector import MetadataModule

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


def _ctx(tmp_path: Path) -> ModuleContext:
    return make_module_context(make_module_config(tmp_path))


async def test_pdf_scan_reports_properties(tmp_path: Path) -> None:
    result = await MetadataModule().run(str(FIXTURE_DIR / "sample.pdf"), _ctx(tmp_path))

    assert result.data["state"] == "ok"
    assert result.data["kind"] == "pdf"
    assert result.data["properties"]["author"] == "Jane Analyst"

    finding = result.findings[0]
    assert finding.title == "Metadata: PDF properties"
    assert finding.severity.value == "info"
    assert finding.data["title"] == "IntelXtract Sample Report"


async def test_image_scan_reports_exif_and_gps(tmp_path: Path) -> None:
    result = await MetadataModule().run(str(FIXTURE_DIR / "sample.jpg"), _ctx(tmp_path))

    assert result.data["kind"] == "image"
    assert result.data["properties"]["camera_make"] == "Canon"

    titles = {finding.title for finding in result.findings}
    assert "Metadata: image properties" in titles
    assert "Metadata: GPS coordinates" in titles
    gps = next(
        finding
        for finding in result.findings
        if finding.title == "Metadata: GPS coordinates"
    )
    assert gps.severity.value == "low"
    assert gps.data["latitude"] == 2.559167


async def test_office_scan_reports_properties(tmp_path: Path) -> None:
    result = await MetadataModule().run(
        str(FIXTURE_DIR / "sample.docx"), _ctx(tmp_path)
    )

    assert result.data["kind"] == "office"
    finding = result.findings[0]
    assert finding.title == "Metadata: office document properties"
    assert finding.data["creator"] == "Jane Analyst"
    assert finding.data["Company"] == "IntelXtract Labs"


async def test_unsupported_extension_is_informational(tmp_path: Path) -> None:
    blob = tmp_path / "notes.txt"
    blob.write_text("plain text", encoding="utf-8")

    result = await MetadataModule().run(str(blob), _ctx(tmp_path))

    assert result.data["state"] == "unsupported"
    assert result.findings[0].title == "Metadata: unsupported file type"
    assert result.findings[0].severity.value == "info"


async def test_malformed_file_fails_gracefully(tmp_path: Path) -> None:
    result = await MetadataModule().run(
        str(FIXTURE_DIR / "malformed.pdf"), _ctx(tmp_path)
    )

    assert result.data["state"] == "error"
    finding = result.findings[0]
    assert finding.title == "Metadata: unparseable document"
    assert finding.severity.value == "low"


async def test_validate_rejects_missing_files(tmp_path: Path) -> None:
    module = MetadataModule()

    assert module.validate(str(FIXTURE_DIR / "sample.pdf")) is True
    assert module.validate(str(tmp_path / "missing.pdf")) is False
