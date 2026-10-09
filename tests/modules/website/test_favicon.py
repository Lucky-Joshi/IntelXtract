"""Favicon fingerprint (Phase 10, S10.3) module tests."""

from __future__ import annotations

from pathlib import Path

from core.constants import Severity, TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from fixtures import favicon_bytes
from modules.website.favicon import FaviconModule, favicon_hash

PAGE_URL = "https://example.com/"
FAV_URL = "https://example.com/favicon.ico"


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.URL)


def test_favicon_hash_is_deterministic() -> None:
    assert favicon_hash(favicon_bytes()) == favicon_hash(favicon_bytes())
    assert favicon_hash(b"A") != favicon_hash(b"B")


async def test_favicon_fingerprint_found(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        FAV_URL,
        body=favicon_bytes(),
        headers={"Content-Type": "image/x-icon"},
    )
    ctx = _ctx(tmp_path, client=client)

    result = await FaviconModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "ok"
    assert result.data["hash"] == favicon_hash(favicon_bytes())
    assert result.data["size"] == len(favicon_bytes())
    assert result.data["content_type"] == "image/x-icon"

    finding = result.findings[0]
    assert finding.title == "Favicon: fingerprint"
    assert finding.data["hash"] == result.data["hash"]
    assert finding.severity is Severity.INFO


async def test_favicon_missing_reports_low(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(FAV_URL, body=None, status=404)
    ctx = _ctx(tmp_path, client=client)

    result = await FaviconModule().run(PAGE_URL, ctx)

    assert result.data["state"] == "missing"
    assert result.findings[0].title == "Favicon: not found"
    assert result.findings[0].severity is Severity.LOW
