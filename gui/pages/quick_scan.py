"""Quick Scan page: one target, fast module set."""

from __future__ import annotations

from gui.pages.scan_page import ScanPage


class QuickScanPage(ScanPage):
    """Single-target quick scan."""

    page_id = "quick_scan"
    title = "Quick Scan"
    mode = "quick"
    with_checklist = False
