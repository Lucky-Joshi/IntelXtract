"""Certificate transparency history via crt.sh (Phase 13, S13.3).

Passive query of public CT logs for certificates issued to a domain:
issuers, validity windows, SAN sets, and first/last seen.  Fetching goes
through the shared HTTP client so unit tests stub the endpoint; the
aggregation (:func:`aggregate_transparency`) is pure and fixture-tested.
"""

from __future__ import annotations

from typing import Any, cast

from core.engine import ModuleContext
from modules.base import BaseModule

_DEFAULT_ENDPOINT = "https://crt.sh"
_MAX_RESULTS = 500


def _normalize_names(raw: str) -> list[str]:
    """Split crt.sh ``name_value`` (newline-separated) into clean names."""
    names: list[str] = []
    for line in raw.replace("\r", "\n").splitlines():
        name = line.strip().lower().rstrip(".")
        if name:
            names.append(name)
    return names


def _parse_timestamp(value: Any) -> str:
    """Return an ISO-8601 string for crt.sh timestamps (best effort)."""
    if isinstance(value, str):
        return value[:19] if "T" in value else value
    return ""


def aggregate_transparency(
    entries: list[dict[str, Any]],
    *,
    domain: str,
    max_results: int = _MAX_RESULTS,
) -> dict[str, Any]:
    """Aggregate crt.sh entries into issuer/validity/SAN history.

    Certificates are deduplicated by ``id`` (falling back to serial number)
    and ordered oldest-first; ``first_seen``/``last_seen`` bound the CT
    window.  SAN sets keep only names belonging to ``domain`` (including
    the apex) so the correlation phase can link related hosts.
    """
    suffix = f".{domain}"
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    issuers: set[str] = set()
    related: set[str] = set()
    first_seen = ""
    last_seen = ""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("id") or entry.get("serial_number") or "")
        if not key:
            key = f"{entry.get('common_name','')}|{entry.get('not_before','')}"
        if key in seen:
            continue
        seen.add(key)
        names = _normalize_names(str(entry.get("name_value", "")))
        issuer = str(entry.get("issuer_name", "")).strip()
        if issuer:
            issuers.add(issuer)
        for name in names:
            plain = name[2:] if name.startswith("*.") else name
            if plain == domain or plain.endswith(suffix):
                related.add(plain)
        not_before = _parse_timestamp(entry.get("not_before"))
        not_after = _parse_timestamp(entry.get("not_after"))
        entry_time = _parse_timestamp(entry.get("entry_timestamp"))
        if not first_seen or (entry_time and entry_time < first_seen):
            first_seen = entry_time or first_seen
        if not last_seen or (entry_time and entry_time > last_seen):
            last_seen = entry_time or last_seen
        records.append(
            {
                "id": key,
                "common_name": str(entry.get("common_name", ""))
                .strip()
                .lower()
                .rstrip("."),
                "issuer": issuer,
                "not_before": not_before,
                "not_after": not_after,
                "names": names,
            }
        )
    records.sort(key=lambda item: (item["not_before"], item["id"]))
    return {
        "domain": domain,
        "count": len(records),
        "issuers": sorted(issuers),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "certificates": records[:max_results],
        "related_names": sorted(related)[:max_results],
    }


async def fetch_transparency(
    module: BaseModule,
    ctx: ModuleContext,
    domain: str,
    *,
    max_results: int = _MAX_RESULTS,
) -> dict[str, Any]:
    """Fetch and aggregate CT history for ``domain`` via crt.sh.

    Network failures are not raised: an empty history is returned so the
    collector can degrade to "unknown" instead of failing the run.
    """
    endpoint = str(ctx.config.get("certificate.endpoint", _DEFAULT_ENDPOINT))
    try:
        payload = await module.http_get_json(
            ctx,
            endpoint,
            params={"q": f"%.{domain}", "output": "json"},
        )
    except Exception:
        return aggregate_transparency([], domain=domain, max_results=max_results)
    entries = cast(list[dict[str, Any]], payload) if isinstance(payload, list) else []
    return aggregate_transparency(entries, domain=domain, max_results=max_results)


__all__ = ["aggregate_transparency", "fetch_transparency"]
