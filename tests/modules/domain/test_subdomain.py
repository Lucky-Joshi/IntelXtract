"""Certificate-transparency (Phase 8, S8.4) subdomain module tests."""

from __future__ import annotations

from pathlib import Path

from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import crt_payload
from modules.domain.subdomain import SubdomainModule, _extract_names

CRT_URL = "https://crt.sh"


async def test_extract_names_filters_dedupes_and_sorts() -> None:
    entries = [
        {"name_value": "*.b.example.com\nexample.com\nrich.example.com"},
        {"name_value": "www.example.com."},
        {"name_value": "evil.other.test"},
        {"name_value": "a.example.com"},
    ]
    assert _extract_names(entries, "example.com", max_results=500) == [
        "a.example.com",
        "b.example.com",
        "rich.example.com",
        "www.example.com",
    ]


async def test_extract_names_respects_max_results() -> None:
    entries = [{"name_value": f"host{i}.example.com"} for i in range(10)]
    assert len(_extract_names(entries, "example.com", max_results=3)) == 3


async def test_subdomain_module_lists_hosts(tmp_path: Path) -> None:
    cfg = make_module_config(tmp_path)
    client = FakeHttpClient()
    client.stub(
        CRT_URL, body=crt_payload(), headers={"content-type": "application/json"}
    )
    ctx = make_module_context(cfg, http=client)

    result = await SubdomainModule().run("example.com", ctx)

    assert result.data["subdomains"] == [
        "a.example.com",
        "b.example.com",
        "rich.example.com",
        "www.example.com",
    ]
    assert result.data["count"] == 4
    assert result.findings[0].title == "Subdomains: certificate transparency"
    assert result.findings[0].data["count"] == 4
