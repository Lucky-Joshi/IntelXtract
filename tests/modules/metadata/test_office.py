"""OOXML office property extraction tests (Phase 14, S14.3/S14.4)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from modules.metadata.office import OfficeMetadataError, extract_ooxml

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "metadata"
CORE_TYPES = (
    """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">"""
    + """</Types>"""
)


def test_extracts_core_and_app_properties() -> None:
    record = extract_ooxml(FIXTURE_DIR / "sample.docx")

    assert record["title"] == "Quarterly Threat Assessment"
    assert record["creator"] == "Jane Analyst"
    assert record["lastModifiedBy"] == "Bob Reviewer"
    assert record["created"] == "2024-01-02T08:00:00Z"
    assert record["modified"] == "2024-02-03T09:30:00Z"
    assert record["Application"] == "Microsoft Office Word"
    assert record["Company"] == "IntelXtract Labs"
    assert record["Manager"] == "Operations"


def test_malformed_zip_raises() -> None:
    with pytest.raises(OfficeMetadataError):
        extract_ooxml(FIXTURE_DIR / "malformed.docx")


def test_container_without_properties_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty.docx"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("[Content_Types].xml", CORE_TYPES)

    with pytest.raises(OfficeMetadataError):
        extract_ooxml(empty)


def test_missing_file_raises() -> None:
    with pytest.raises(OfficeMetadataError):
        extract_ooxml(FIXTURE_DIR / "does-not-exist.docx")
