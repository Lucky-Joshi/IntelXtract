"""Static, hand-recorded fixtures for Phase 8 network modules (no I/O).

Each JSON file mirrors a real upstream response shape (RDAP, DoH JSON,
crt.sh, HTTP probes) so the domain-module tests exercise realistic payloads
without touching the network.  ``doh_handler``/``http_handler`` produce the
callable ``(status, headers, body)`` stubs consumed by
:class:`fakes.FakeHttpClient`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, cast

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

StubHandler = Callable[[str, str, dict[str, Any]], tuple[int, dict[str, str], Any]]


@cache
def _load(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def rdap_payload() -> dict[str, Any]:
    """RDAP response for ``example.com`` (whois module)."""
    return cast(dict[str, Any], _load("rdap.json"))


def crt_payload() -> list[dict[str, Any]]:
    """crt.sh JSON entries for ``example.com`` (subdomain module)."""
    return cast(list[dict[str, Any]], _load("crt.json"))


def geo_payload() -> dict[str, Any]:
    """ip-api.org success payload for ``1.1.1.1`` (geo module)."""
    return cast(dict[str, Any], _load("geo.json"))


def doh_answer(data: str, *, rtype: int = 1, name: str = "") -> dict[str, Any]:
    """Build a minimal DoH JSON response carrying one answer record."""
    return cast(
        dict[str, Any],
        {
            "Status": 0,
            "Answer": [{"name": name, "type": rtype, "TTL": 60, "data": data}],
        },
    )


def doh_handler() -> StubHandler:
    """DoH JSON responses keyed by ``(name, type)`` query pair (dns module)."""
    table: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _load("doh.json"):
        query = item["query"]
        table[(query["name"], query["type"])] = item["response"]

    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        params = kwargs.get("params") or {}
        name = params.get("name")
        dns_type = params.get("type")
        key = (
            name if isinstance(name, str) else "",
            dns_type if isinstance(dns_type, str) else "",
        )
        response = table.get(key)
        if response is None:
            return 200, {"content-type": "application/dns-json"}, {"Status": 0}
        return 200, {"content-type": "application/dns-json"}, response

    return _handle


def http_handler() -> StubHandler:
    """HTTP probe responses keyed by exact URL (http module)."""
    table = _load("http.json")

    def _handle(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], Any]:
        entry = table.get(url)
        if entry is None:
            return 404, {"content-type": "text/plain"}, "not found"
        return entry["status"], entry["headers"], entry["body"]

    return _handle
