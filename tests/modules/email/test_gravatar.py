"""Phase 11 S11.3: Gravatar hash and existence probe."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from core.constants import TargetType
from core.engine import ModuleContext
from fakes import FakeHttpClient, make_module_config, make_module_context
from modules.email.gravatar import gravatar_hash, probe_gravatar

GRAVATAR_URL = "https://www.gravatar.com/avatar/"
ALICE = "Alice@Example.com"


def _ctx(tmp_path: Path, *, client: FakeHttpClient) -> ModuleContext:
    cfg = make_module_config(tmp_path)
    return make_module_context(cfg, http=client, target_type=TargetType.EMAIL)


def test_gravatar_hash_is_normalized_md5() -> None:
    digest = gravatar_hash(ALICE)
    expected = hashlib.md5(b"alice@example.com", usedforsecurity=False).hexdigest()
    assert digest == expected
    assert len(digest) == 32
    assert gravatar_hash("alice@example.com") == digest
    assert gravatar_hash("ALICE@example.com") == digest


async def test_gravatar_exists(tmp_path: Path) -> None:
    client = FakeHttpClient()
    digest = gravatar_hash(ALICE)
    client.stub(f"{GRAVATAR_URL}{digest}", status=200)
    result = await probe_gravatar(_ctx(tmp_path, client=client), ALICE)
    assert result["state"] == "ok"
    assert result["exists"] is True
    assert result["hash"] == digest


async def test_gravatar_absent(tmp_path: Path) -> None:
    client = FakeHttpClient()
    result = await probe_gravatar(_ctx(tmp_path, client=client), ALICE)
    assert result["state"] == "ok"
    assert result["exists"] is False


async def test_gravatar_transport_error_degrades(tmp_path: Path) -> None:
    client = FakeHttpClient()
    digest = gravatar_hash(ALICE)

    def _boom(
        method: str, url: str, kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, str], bytes]:
        raise RuntimeError("connection refused")

    client.stub(f"{GRAVATAR_URL}{digest}", body=_boom)
    result = await probe_gravatar(_ctx(tmp_path, client=client), ALICE)
    assert result["state"] == "unavailable"
    assert result["exists"] is None
