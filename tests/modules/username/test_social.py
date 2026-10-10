"""Phase 12 S12.2: verdict resolution across mocked response types."""

from __future__ import annotations

from pathlib import Path

from core.constants import TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.username.sites import validate_site
from modules.username.social import (
    VERDICT_EXISTS,
    VERDICT_MISSING,
    VERDICT_UNKNOWN,
    check_sites,
    probe_site,
)

GITHUB = validate_site(
    {
        "name": "GitHub",
        "url": "https://github.com/{username}",
        "rule": {"exists": [200], "missing": [404]},
    }
)
INSTAGRAM = validate_site(
    {
        "name": "Instagram",
        "url": "https://www.instagram.com/{username}/",
        "rule": {
            "exists": [200],
            "missing": [404],
            "missing_marker": "page isn't available",
        },
    }
)
REDDIT = validate_site(
    {
        "name": "Reddit",
        "url": "https://www.reddit.com/user/{username}",
        "rule": {"exists": [200], "missing": [], "unknown": [403, 410]},
    }
)


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.USERNAME)


async def test_probe_exists(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://github.com/octocat", status=200, body="<html>...</html>")
    result = await probe_site(_ctx(tmp_path, client=client), GITHUB, "octocat")
    assert result["verdict"] == VERDICT_EXISTS
    assert result["status"] == 200
    assert result["url"] == "https://github.com/octocat"


async def test_probe_missing(tmp_path: Path) -> None:
    client = FakeHttpClient()
    result = await probe_site(_ctx(tmp_path, client=client), GITHUB, "ghost")
    assert result["verdict"] == VERDICT_MISSING
    assert result["status"] == 404


async def test_probe_blocked_is_unknown(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://www.reddit.com/user/nobody", status=403, body="blocked")
    result = await probe_site(_ctx(tmp_path, client=client), REDDIT, "nobody")
    assert result["verdict"] == VERDICT_UNKNOWN
    assert result["status"] == 403


async def test_probe_unexpected_status_is_unknown(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://github.com/weird", status=503, body="back soon")
    result = await probe_site(_ctx(tmp_path, client=client), GITHUB, "weird")
    assert result["verdict"] == VERDICT_UNKNOWN
    assert result["marker_hit"] is None


async def test_probe_marker_overrides_status(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        "https://www.instagram.com/ghost/",
        status=200,
        body="<title>Instagram</title> Sorry, this page isn't available.",
    )
    result = await probe_site(_ctx(tmp_path, client=client), INSTAGRAM, "ghost")
    assert result["verdict"] == VERDICT_MISSING
    assert result["status"] == 200
    assert result["marker_hit"] == "page isn't available"


async def test_probe_transport_error_is_unknown(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def _boom(
        method: str, url: str, kwargs: dict[str, object]
    ) -> tuple[int, dict[str, str], bytes]:
        raise RuntimeError("dns failed")

    client.stub("https://github.com/offline", body=_boom)
    result = await probe_site(_ctx(tmp_path, client=client), GITHUB, "offline")
    assert result["verdict"] == VERDICT_UNKNOWN
    assert result["status"] is None


async def test_check_sites_batches_and_paces(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://github.com/octocat", status=200)
    client.stub("https://www.instagram.com/octocat/", status=404)
    results = await check_sites(
        _ctx(tmp_path, client=client),
        [GITHUB, INSTAGRAM],
        "octocat",
        concurrency=2,
        per_site_interval=0.0,
    )
    by_name = {r["name"]: r["verdict"] for r in results}
    assert by_name["GitHub"] == VERDICT_EXISTS
    assert by_name["Instagram"] == VERDICT_MISSING
