"""Small helpers shared by the Phase 10 website collectors (private)."""

from __future__ import annotations

from urllib.parse import urlsplit


def origin(target: str) -> str:
    """Return ``scheme://netloc`` for a normalized target URL."""
    parts = urlsplit(target)
    return f"{parts.scheme}://{parts.netloc}"


def absolute(target: str, path: str) -> str:
    """Join a target's origin with a root-relative ``path``."""
    if not path.startswith("/"):
        path = f"/{path}"
    return origin(target) + path
