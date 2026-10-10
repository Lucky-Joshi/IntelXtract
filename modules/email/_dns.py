"""Shared DNS-over-HTTPS helpers for Phase 11 (private module).

Reuses the same ``application/dns-json`` naming the IP module uses so the
email collectors need no raw DNS sockets, and so tests stub a single DoH
endpoint.
"""

from __future__ import annotations

from typing import Any

from core.engine import ModuleContext


async def query_answers(
    ctx: ModuleContext, endpoint: str, name: str, rtype: str
) -> list[dict[str, Any]]:
    """Run a DNS-over-HTTPS JSON lookup and return the ``Answer`` list."""
    if ctx.http is None:
        raise RuntimeError("module requires ctx.http to perform requests")
    payload = await ctx.http.get_json(
        endpoint,
        params={"name": name, "type": rtype},
        headers={"Accept": "application/dns-json"},
    )
    if not isinstance(payload, dict):
        return []
    answers = payload.get("Answer")
    if not isinstance(answers, list):
        return []
    return [answer for answer in answers if isinstance(answer, dict)]


async def txt_values(ctx: ModuleContext, endpoint: str, name: str) -> list[str]:
    """Return the flattened TXT record strings for ``name``."""
    answers = await query_answers(ctx, endpoint, name, "TXT")
    values: list[str] = []
    for answer in answers:
        for raw in answer.get("data", "").split('"'):
            if raw and not raw.isspace():
                values.append(raw)
    return values
