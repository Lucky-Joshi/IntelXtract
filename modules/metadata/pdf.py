"""PDF property extraction (Phase 14, S14.1) via ``pypdf``.

Reads only the document-identification trailer/dictionaries — never pixel
content — and projects the handful of fields the report model cares about:
title, author, producer, creator, subject, page count, PDF version, and
creation/modification times (normalized to ISO-8601).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pypdf
from pypdf.errors import PyPdfError


class PdfMetadataError(ValueError):
    """Raised when a file cannot be opened or decoded as PDF."""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _iso(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return ""
    return value.isoformat(timespec="seconds")


def extract_pdf(path: str | Path) -> dict[str, Any]:
    """Return projectable PDF properties, raising on unreadable files."""
    try:
        reader = pypdf.PdfReader(path)
    except (PyPdfError, ValueError, OSError, TypeError) as exc:
        raise PdfMetadataError(f"unreadable PDF: {exc}") from exc

    metadata = reader.metadata
    record = {
        "pdf_version": str(reader.pdf_header).replace("%PDF-", "").strip(),
        "page_count": len(reader.pages),
        "title": _clean(getattr(metadata, "title", "")),
        "author": _clean(getattr(metadata, "author", "")),
        "producer": _clean(getattr(metadata, "producer", "")),
        "creator": _clean(getattr(metadata, "creator", "")),
        "subject": _clean(getattr(metadata, "subject", "")),
        "created": _iso(getattr(metadata, "creation_date", None)),
        "modified": _iso(getattr(metadata, "modification_date", None)),
    }
    return {key: value for key, value in record.items() if value != ""}


__all__ = ["PdfMetadataError", "extract_pdf"]
