"""OOXML document property extraction (Phase 14, S14.3).

Office 2007+ files (``.docx``/``.xlsx``/``.pptx``) are zip archives; the
core and extended-property parts are plain XML read straight from the
container — no OPC library or external tooling required.  Legacy binary
``.doc`` files are explicitly out of scope for v1.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

_CORE_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
}
_APP_NS = {
    "ap": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
}

_CORE_FIELDS = (
    ("cp", "category"),
    ("cp", "contentStatus"),
    ("dc", "creator"),
    ("cp", "lastModifiedBy"),
    ("dc", "title"),
    ("dc", "subject"),
    ("dc", "description"),
    ("dcterms", "created"),
    ("dcterms", "modified"),
    ("cp", "revision"),
)
_APP_FIELDS = (
    ("ap", "Application"),
    ("ap", "AppVersion"),
    ("ap", "Company"),
    ("ap", "Manager"),
    ("ap", "TotalTime"),
)


class OfficeMetadataError(ValueError):
    """Raised when a file is not a readable OOXML container."""


def _expression(namespaces: dict[str, str], prefix: str, local: str) -> str:
    return f"{{{namespaces[prefix]}}}{local}"


def _query(root: ElementTree.Element, expr: str, namespaces: dict[str, str]) -> str:
    try:
        element = root.find(expr, namespaces)
    except ElementTree.ParseError:
        return ""
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _collect(
    xml_text: str,
    namespaces: dict[str, str],
    fields: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    if not xml_text:
        return {}
    try:
        root = ElementTree.fromstring(  # noqa: S314 - docs supply the container, values only feed findings
            xml_text
        )
    except ElementTree.ParseError:
        return {}
    record: dict[str, Any] = {}
    for prefix, local in fields:
        value = _query(root, _expression(namespaces, prefix, local), namespaces)
        if value:
            record[local] = value
    return record


def extract_ooxml(path: str | Path) -> dict[str, Any]:
    """Project core/app properties from a ``.docx``/``.xlsx``/``.pptx`` file."""
    try:
        with zipfile.ZipFile(path) as archive:
            core_raw = _read_text(archive, "docProps/core.xml")
            app_raw = _read_text(archive, "docProps/app.xml")
    except (zipfile.BadZipFile, OSError) as exc:
        raise OfficeMetadataError(f"unreadable OOXML container: {exc}") from exc

    core = _collect(core_raw, _CORE_NS, _CORE_FIELDS)
    app = _collect(app_raw, _APP_NS, _APP_FIELDS)

    record = {**core, **app}
    if not record:
        raise OfficeMetadataError("document carries no core/app properties")
    return record


def _read_text(zip_root: zipfile.ZipFile, name: str) -> str:
    try:
        return zip_root.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return ""


__all__ = ["OfficeMetadataError", "extract_ooxml"]
