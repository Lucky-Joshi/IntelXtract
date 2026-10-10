"""Phase 19 (S19.2): brand tokens loaded from ``BRAND.md`` with defaults."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
BRAND_FILE = _REPO_ROOT / "BRAND.md"

DEFAULTS: dict[str, str] = {
    "name": "IntelXtract",
    "tagline": "OSINT reconnaissance report",
    "accent": "#1f6feb",
    "accent_soft": "#dbeafe",
    "page_background": "#ffffff",
    "card_background": "#f6f8fa",
    "text": "#24292f",
    "muted": "#6a737d",
    "border": "#d0d7de",
}


def brand_tokens() -> dict[str, str]:
    """Read ``Key: value`` tokens from ``BRAND.md``, merged over defaults."""
    tokens = dict(DEFAULTS)
    if not BRAND_FILE.exists():
        return tokens
    for line in BRAND_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if ":" not in stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()
        if key and value:
            tokens[key] = value
    return tokens


__all__ = ["BRAND_FILE", "brand_tokens"]
