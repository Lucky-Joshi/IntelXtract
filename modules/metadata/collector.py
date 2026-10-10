"""Metadata module collector (Phase 14, S14.1-S14.4).

Dispatches a user-provided file to the matching extractor and projects the
record into findings.  Malformed files never crash a scan — they collapse
to an informational ``unparseable`` state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.models import Finding, ModuleResult, make_finding
from modules.base import BaseModule
from modules.metadata.image import ImageMetadataError, extract_image
from modules.metadata.office import OfficeMetadataError, extract_ooxml
from modules.metadata.pdf import PdfMetadataError, extract_pdf

_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
)
_OFFICE_EXTENSIONS = frozenset({".docx", ".xlsx", ".pptx"})

_SUMMARY_FIELDS = {
    "pdf": ("title", "author", "producer", "creator", "subject"),
    "image": ("camera_make", "camera_model", "software", "datetime"),
    "office": ("title", "creator", "lastModifiedBy", "Company"),
}


class MetadataModule(BaseModule):
    """Document/file metadata extraction (PDF, images, OOXML office files)."""

    name = "metadata"
    target_types = (TargetType.FILE,)
    description = "document metadata: PDF / image EXIF / OOXML office properties"
    timeout = 15.0

    def validate(self, target: str) -> bool:
        return Path(target).is_file()

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        path = Path(target)
        extension = path.suffix.lower()

        try:
            if extension == ".pdf":
                record, kind = extract_pdf(path), "pdf"
            elif extension in _IMAGE_EXTENSIONS:
                record, kind = extract_image(path), "image"
            elif extension in _OFFICE_EXTENSIONS:
                record, kind = extract_ooxml(path), "office"
            else:
                return self._unsupported(path)
        except (PdfMetadataError, ImageMetadataError, OfficeMetadataError) as exc:
            return self._unparseable(path, exc)

        findings = self._findings(kind, path.name, record)
        return ModuleResult(
            data={
                "target": path.name,
                "kind": kind,
                "properties": record,
                "state": "ok",
            },
            findings=findings,
        )

    def _unsupported(self, path: Path) -> ModuleResult:
        finding = make_finding(
            self.name,
            "Metadata: unsupported file type",
            {"filename": path.name, "extension": path.suffix.lower()},
            severity=Severity.INFO,
            confidence=0.9,
            evidence=f"no extractor for {path.suffix.lower() or 'unknown'} files",
        )
        return ModuleResult(
            data={"target": path.name, "kind": "unknown", "state": "unsupported"},
            findings=[finding],
        )

    def _unparseable(self, path: Path, exc: Exception) -> ModuleResult:
        finding = make_finding(
            self.name,
            "Metadata: unparseable document",
            {"filename": path.name, "error": str(exc)},
            severity=Severity.LOW,
            confidence=0.6,
            evidence=str(exc),
        )
        return ModuleResult(
            data={"target": path.name, "kind": "unknown", "state": "error"},
            findings=[finding],
        )

    def _findings(self, kind: str, name: str, record: dict[str, Any]) -> list[Finding]:
        titles = {
            "pdf": "Metadata: PDF properties",
            "image": "Metadata: image properties",
            "office": "Metadata: office document properties",
        }
        finding = make_finding(
            self.name,
            titles[kind],
            {
                "filename": name,
                **{key: record[key] for key in _SUMMARY_FIELDS[kind] if key in record},
            },
            severity=Severity.INFO,
            confidence=0.9,
            evidence=f"{len(record)} attribute(s) extracted",
        )
        if kind != "image" or record.get("gps") is None:
            return [finding]
        gps = record["gps"]
        gps_finding = make_finding(
            self.name,
            "Metadata: GPS coordinates",
            {"filename": name, **gps},
            severity=Severity.LOW,
            confidence=0.7,
            evidence=f"{gps['latitude']},{gps['longitude']}",
        )
        return [finding, gps_finding]


__all__ = ["MetadataModule"]
