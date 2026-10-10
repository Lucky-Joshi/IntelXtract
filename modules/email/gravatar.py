"""S11.3 — Gravatar existence probe via the public avatar endpoint.

The hash is ``md5(lowercased email)`` (Gravatar's published convention,
non-security use); a ``d=404`` request returns 404 for unknown users.
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.engine import ModuleContext
from modules.email.validation import normalize_email

DEFAULT_GRAVATAR_ENDPOINT = "https://www.gravatar.com/avatar/"


def gravatar_hash(email: str) -> str:
    """Return Gravatar's hex MD5 of the normalized address."""
    digest = hashlib.md5(
        normalize_email(email).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return digest


async def probe_gravatar(ctx: ModuleContext, email: str) -> dict[str, Any]:
    """Probe ``d=404`` for existence; degrade gracefully on transport errors."""
    endpoint = str(ctx.config.get("email.gravatar_endpoint", DEFAULT_GRAVATAR_ENDPOINT))
    digest = gravatar_hash(email)
    url = f"{endpoint}{digest}"
    result: dict[str, Any] = {
        "exists": None,
        "hash": digest,
        "url": f"https://gravatar.com/{digest}",
        "endpoint": endpoint,
    }
    if ctx.http is None:
        result["state"] = "unavailable"
        return result
    try:
        response = await ctx.http.request("GET", url, params={"d": "404", "s": "80"})
    except Exception:
        result["state"] = "unavailable"
        return result
    if response.status == 200:
        result["exists"] = True
        result["profile"] = f"https://www.gravatar.com/{digest}.json"
    else:
        result["exists"] = False
    result["state"] = "ok"
    return result
