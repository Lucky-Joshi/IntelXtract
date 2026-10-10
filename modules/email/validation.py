"""S11.1 — address syntax, structure, and disposable-domain classification.

Pure functions, no network access: the collector calls these before deciding
whether to probe mail infrastructure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from modules.email._disposable import BUNDLED_DISPOSABLE_DOMAINS

_EMAIL_RE = re.compile(
    r"^[^@\s]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$"
)


def normalize_email(raw: str) -> str:
    """Trim and lowercase an address for canonical comparisons/hashes."""
    return raw.strip().lower()


def syntax_valid(raw: str) -> bool:
    """True when ``raw`` looks like a well-formed email address."""
    return bool(_EMAIL_RE.match(raw.strip()))


def domain_of(raw: str) -> str | None:
    """Return the registrable-looking domain portion, else ``None``."""
    if not syntax_valid(raw):
        return None
    return normalize_email(raw).split("@", 1)[1]


def local_part(raw: str) -> str | None:
    """Return the local part, else ``None``."""
    if not syntax_valid(raw):
        return None
    return normalize_email(raw).split("@", 1)[0]


def is_disposable(domain: str | None, extra: Iterable[str] = ()) -> bool:
    """True when ``domain`` is a known disposable provider.

    ``extra`` merges operator-supplied domains (from config) over the bundled
    list so deployments can extend the blocklist without a code release.
    """
    if domain is None:
        return False
    lowered = domain.strip().lower().rstrip(".")
    if lowered in BUNDLED_DISPOSABLE_DOMAINS:
        return True
    extras = {d.strip().lower().rstrip(".") for d in extra if d and d.strip()}
    return lowered in extras


def classify(raw: str, disposable_extra: Iterable[str] = ()) -> dict[str, Any]:
    """Return ``(syntax, local, domain, disposable)`` in one structured pass."""
    valid = syntax_valid(raw)
    local = local_part(raw) if valid else None
    domain = domain_of(raw) if valid else None
    return {
        "syntax": valid,
        "local": local,
        "domain": domain,
        "disposable": is_disposable(domain, disposable_extra) if valid else False,
    }
