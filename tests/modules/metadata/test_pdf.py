"""PDF metadata extraction tests (Phase 14, S14.1/S14.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.metadata.pdf import PdfMetadataError, extract_pdf

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "metadata"


def test_extracts_expected_pdf_fields() -> None:
    record = extract_pdf(FIXTURE_DIR / "sample.pdf")

    assert record["pdf_version"] == "1.3"
    assert record["page_count"] == 1
    assert record["title"] == "IntelXtract Sample Report"
    assert record["author"] == "Jane Analyst"
    assert record["producer"] == "IntelXtract Generator"
    assert record["creator"] == "pypdf"
    assert record["subject"] == "Phase 14 fixture document"
    assert record["created"] == "2024-01-02T12:34:56+00:00"
    assert record["modified"] == "2024-02-03T11:22:33+00:00"


def test_malformed_pdf_raises() -> None:
    with pytest.raises(PdfMetadataError):
        extract_pdf(FIXTURE_DIR / "malformed.pdf")


def test_missing_pdf_raises() -> None:
    with pytest.raises(PdfMetadataError):
        extract_pdf(FIXTURE_DIR / "does-not-exist.pdf")
