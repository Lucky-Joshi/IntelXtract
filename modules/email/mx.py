"""S11.2 — mail-domain DNS probes: MX presence, SPF, DMARC, MX resolution.

Query-only; findings and severities are the collector's job so this module
stays reusable and unit-testable against a stubbed DoH endpoint.
"""

from __future__ import annotations

import re
from typing import Any

from core.engine import ModuleContext
from modules.email._dns import query_answers, txt_values

_SPF_INCLUDE_RE = re.compile(r"\binclude:([A-Za-z0-9._-]+)")
_SPF_ALL_RE = re.compile(r"([-~+?]?)all\b")
_DMARC_ITEM_RE = re.compile(r"\b([A-Za-z]+)=([^;\s]+)")

_DMARC_POLICIES = {
    "none": "no action, mail accepted regardless",
    "quarantine": "treat failures as suspicious",
    "reject": "refuse mail failing DMARC",
}

DEFAULT_DNS_ENDPOINT = "https://cloudflare-dns.com/dns-query"


async def mx_records(
    ctx: ModuleContext, endpoint: str, domain: str
) -> list[dict[str, Any]]:
    """Return sorted ``[{"priority", "host", "a": [...]}]`` MX records."""
    answers = await query_answers(ctx, endpoint, domain, "MX")
    records: list[dict[str, Any]] = []
    for answer in answers:
        data = str(answer.get("data", ""))
        parts = data.strip().strip(".").split()
        if len(parts) != 2:
            continue
        priority, host = parts
        records.append({"priority": int(priority), "host": host.rstrip("."), "a": []})
    records.sort(key=lambda item: item["priority"])
    for record in records:
        a_answers = await query_answers(ctx, endpoint, record["host"], "A")
        record["a"] = [str(a.get("data", "")).rstrip(".") for a in a_answers]
    return records


def parse_spf(txts: list[str]) -> dict[str, Any] | None:
    """Locate and parse the ``v=spf1`` record, else ``None``."""
    for txt in txts:
        if not txt.strip().lower().startswith("v=spf1"):
            continue
        all_match = _SPF_ALL_RE.search(txt)
        return {
            "raw": txt,
            "include": [m.group(1) for m in _SPF_INCLUDE_RE.finditer(txt)],
            "all": all_match.group(1) if all_match else None,
        }
    return None


def parse_dmarc(txts: list[str]) -> dict[str, Any] | None:
    """Locate and parse the ``v=DMARC1`` record, else ``None``."""
    for txt in txts:
        if not txt.strip().lower().startswith("v=dmarc1"):
            continue
        items = {key.lower(): value for key, value in _DMARC_ITEM_RE.findall(txt)}
        policy = items.get("p")
        return {
            "raw": txt,
            "policy": policy,
            "policy_note": _DMARC_POLICIES.get(policy, "") if policy else "",
            "percent": (int(items["pct"]) if items.get("pct", "").isdigit() else None),
        }
    return None


async def probe_mail_dns(ctx: ModuleContext, domain: str) -> dict[str, Any]:
    """Gather MX/SPF/DMARC for ``domain`` in one network pass."""
    endpoint = str(ctx.config.get("email.dns_endpoint", DEFAULT_DNS_ENDPOINT))
    mx = await mx_records(ctx, endpoint, domain)
    txts = await txt_values(ctx, endpoint, domain)
    dmarc_txts = await txt_values(ctx, endpoint, f"_dmarc.{domain}")
    return {
        "mx": mx,
        "spf": parse_spf(txts),
        "dmarc": parse_dmarc(dmarc_txts),
        "endpoint": endpoint,
    }
