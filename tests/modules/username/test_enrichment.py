"""Phase 12 S12.3: GitHub parse-light enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.username.enrichment import GITHUB_API_URL, github_profile

API_URL = GITHUB_API_URL.replace("{username}", "octocat")


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.USERNAME)


async def test_github_profile_parsed(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(
        API_URL,
        status=200,
        body=(
            '{"login": "octocat", "name": "Mona Lisa", "avatar_url": '
            '"https://avatars/1.png", "html_url": "https://github.com/octocat", '
            '"bio": "Hello", "public_repos": 8, "followers": 9000, "nope": 1}'
        ),
    )
    profile = await github_profile(_ctx(tmp_path, client=client), "octocat")
    assert profile["login"] == "octocat"
    assert profile["name"] == "Mona Lisa"
    assert profile["public_repos"] == 8
    assert "nope" not in profile


async def test_github_profile_rate_limited_is_empty(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(API_URL, status=403, body="")
    assert await github_profile(_ctx(tmp_path, client=client), "octocat") == {}


async def test_github_profile_bad_payload_is_empty(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub(API_URL, status=200, body="<html>not json</html>")
    assert await github_profile(_ctx(tmp_path, client=client), "octocat") == {}


async def test_github_profile_transport_error_is_empty(tmp_path: Path) -> None:
    client = FakeHttpClient()

    def _boom(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], bytes]:
        raise RuntimeError("connection reset")

    client.stub(API_URL, body=_boom)
    assert await github_profile(_ctx(tmp_path, client=client), "octocat") == {}
