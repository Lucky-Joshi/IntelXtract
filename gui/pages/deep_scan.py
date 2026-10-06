"""Deep Scan page: full module set with a module checklist."""

from __future__ import annotations

from gui.pages.scan_page import ScanPage


class DeepScanPage(ScanPage):
    """Deep scan with per-module selection."""

    page_id = "deep_scan"
    title = "Deep Scan"
    mode = "deep"
    with_checklist = True
