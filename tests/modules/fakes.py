"""Reusable Phase 7 module test doubles.

Phase 8+ collectors and their tests import these from anywhere under
``tests/modules/**`` (pytest rootdir insertion puts this directory first on
sys.path): ``from fakes import DummyModule, FakeHttpClient,
make_module_context``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from core.cache import AsyncTTLCache
from core.config import Config
from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.http_client import HttpClient
from core.models import ModuleResult, make_finding
from modules.base import BaseModule

HARNESS_SCAN_ID = "harness000000"
HARNESS_LOGGER = logging.getLogger("intelxtract.tests.modules")


class HttpError(Exception):
    """Raised by :class:`FakeHttpClient` for non-2xx responses."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"{url} -> HTTP {status}")
        self.status = status
        self.url = url


class FakeHttpClient:
    """Stub HTTP client that records requests and serves canned responses."""

    def __init__(self) -> None:
        self._responses: dict[str, tuple[int, Any]] = {}
        self.requests: list[dict[str, Any]] = []
        self.aclosed = False

    def stub(self, url: str, *, body: Any = None, status: int = 200) -> None:
        """Serve ``body`` (JSON/list/text/bytes) for exact ``url`` matches."""
        self._responses[url] = (status, body)

    async def _record(self, method: str, url: str, kwargs: dict[str, Any]) -> Any:
        self.requests.append({"method": method, "url": url, "kwargs": kwargs})
        status, body = self._responses.get(url, (404, None))
        if status >= 400:
            raise HttpError(status, url)
        return body

    async def get(self, url: str, **kwargs: Any) -> bytes:
        body = await self._record("GET", url, kwargs)
        if body is None:
            return b""
        return body.encode() if isinstance(body, str) else bytes(body)

    async def get_text(self, url: str, **kwargs: Any) -> str:
        body = await self._record("GET", url, kwargs)
        if body is None:
            return ""
        return body.decode() if isinstance(body, bytes) else str(body)

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        return await self._record("GET", url, kwargs)

    async def aclose(self) -> None:
        self.aclosed = True


def make_module_config(
    path: Path, *, key: str = "hibp", secret: str = "HIBP-SECRET-1234"
) -> Config:
    """Build a tmp-backed config with an ``api_keys.<key>`` entry set."""
    cfg = Config(path, use_env=False)
    cfg.set(f"api_keys.{key}", secret)
    return cfg


def make_module_context(
    config: Config,
    *,
    cache: AsyncTTLCache | None = None,
    http: FakeHttpClient | None = None,
    scan_id: str = HARNESS_SCAN_ID,
    target_type: TargetType = TargetType.DOMAIN,
    extras: dict[str, Any] | None = None,
) -> ModuleContext:
    """Build a Phase 7 :class:`ModuleContext` wired to harness doubles."""
    return ModuleContext(
        config=config,
        cache=cache or AsyncTTLCache(max_size=16, default_ttl=60.0),
        logger=HARNESS_LOGGER,
        scan_id=scan_id,
        target_type=target_type,
        extras=dict(extras or {}),
        http=cast(HttpClient, http) if http is not None else None,
    )


class DummyModule(BaseModule):
    """Deterministic collector proving the Phase 7 contract end-to-end."""

    name = "dummy"
    target_types = (TargetType.DOMAIN, TargetType.IP, TargetType.URL)
    description = "phase-7 harness collector"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        hits = int(await ctx.cache.get(f"dummy:{target}", 0)) + 1
        await ctx.cache.set(f"dummy:{target}", hits)
        data: dict[str, Any] = {"target": target, "hits": hits}
        if ctx.get("dummy.http") and ctx.http is not None:
            data["raw"] = await ctx.http.get_text(f"https://dummy.local/{target}")
        return ModuleResult(
            data=data,
            findings=[
                make_finding(
                    self.name,
                    f"dummy hit {hits} for {target}",
                    {"target": target, "hits": hits},
                    severity=Severity.LOW,
                    confidence=0.9,
                    evidence=f"parsed:{target}",
                )
            ],
        )


class KeyedDummyModule(BaseModule):
    """Collector that refuses to plan without its API key."""

    name = "dummy_keyed"
    target_types = (TargetType.DOMAIN,)
    requires_keys = ("hibp",)
    description = "phase-7 harness collector requiring api_keys.hibp"

    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        key = ctx.api_key("hibp")
        return ModuleResult(
            data={"key_provided": bool(key), "key_hint": (key[:4] if key else None)},
            findings=[
                make_finding(
                    self.name,
                    "keyed dummy",
                    {"key_len": len(key) if key else 0},
                )
            ],
        )
