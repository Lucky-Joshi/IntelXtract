"""S12.3 — parse-light public-profile enrichment.

Only GitHub is enriched: its public JSON API needs no auth token, and the
profile page is theirs to serve.  Non-2xx or blocks yield ``{}`` so
enrichment never fails a scan.
"""

from __future__ import annotations

import json
from typing import Any

from core.engine import ModuleContext

GITHUB_API_URL = "https://api.github.com/users/{username}"


async def github_profile(ctx: ModuleContext, username: str) -> dict[str, Any]:
    """Fetch and validate the public GitHub profile, else ``{}``."""
    if ctx.http is None:
        return {}
    try:
        response = await ctx.http.request(
            "GET",
            GITHUB_API_URL.replace("{username}", username),
            headers={"Accept": "application/vnd.github+json"},
            allow_redirects=True,
        )
    except Exception:
        return {}
    if response.status != 200 or not response.body:
        return {}
    try:
        payload = json.loads(response.body.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    keys = ("login", "name", "avatar_url", "html_url", "bio", "blog", "location")
    profile = {key: payload[key] for key in keys if isinstance(payload.get(key), str)}
    for key in ("public_repos", "followers"):
        value = payload.get(key)
        if isinstance(value, int):
            profile[key] = value
    return profile
