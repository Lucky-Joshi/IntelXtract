"""Shared DoH helpers for the Phase 9 IP collectors (private module).

Reverse-name construction (``in-addr.arpa`` / ``ip6.arpa``) and DNSBL labels
plus a small DNS-over-HTTPS JSON answer helper, so the rdns and reputation
modules need no raw DNS sockets.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from core.engine import ModuleContext


def reverse_name(ip: str) -> str:
    """Return the DNSSEC-style reverse label for an IPv4 or IPv6 address.

    IPv4 -> ``o3.o2.o1.o0.in-addr.arpa``
    IPv6 -> the 32 nibbles of the expanded form, reversed, plus ``ip6.arpa``
    """
    address = ipaddress.ip_address(ip)
    if address.version == 4:
        octets = str(address).split(".")
        return ".".join(reversed(octets)) + ".in-addr.arpa"
    expanded = address.exploded.replace(":", "")
    return ".".join(reversed(expanded)) + ".ip6.arpa"


def dnsbl_name(ip: str, zone: str) -> str | None:
    """Return the DNSBL query label for an IPv4 address, else ``None``.

    Spamhaus ZEN and friends use the ``reversed-octets.<zone>`` convention.
    IPv6 addresses have no ZEN coverage, so callers degrade gracefully
    instead of issuing a pointless query.
    """
    address = ipaddress.ip_address(ip)
    if address.version != 4:
        return None
    octets = str(address).split(".")
    return ".".join(reversed(octets)) + "." + zone.strip(".")


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
