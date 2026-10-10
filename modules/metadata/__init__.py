"""Metadata module (Phase 14): document/file property extraction.

Subpackages cover the three supported families — PDF (pypdf), images
(Pillow, EXIF), and OOXML office documents (zip + XML).  Every extractor
takes a file ``Path`` and never touches the network; controllers catch
malformed input and degrade to an informational finding.
"""

from __future__ import annotations

from modules.metadata.collector import MetadataModule

__all__ = ["MetadataModule"]
