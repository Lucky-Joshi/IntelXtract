"""Reusable Phase 7 module test doubles.

Phase 8+ collectors and their tests import these from anywhere under
``tests/modules/**`` (pytest rootdir insertion puts this directory first on
sys.path): ``from fakes import DummyModule, FakeHttpClient,
make_module_context``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

from core.cache import AsyncTTLCache
from core.config import Config
from core.constants import Severity, TargetType
from core.engine import ModuleContext
from core.http_client import HttpClient, HttpResponse
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
        self._responses: dict[str, tuple[int, dict[str, str], Any]] = {}
        self.requests: list[dict[str, Any]] = []
        self.aclosed = False

    def stub(
        self,
        url: str,
        *,
        body: Any = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Serve ``body`` (JSON/list/text/bytes) for exact ``url`` matches.

        ``body`` may also be a callable ``handler(method, url, kwargs)`` that
        returns a ``(status, headers, body)`` triple — useful for endpoints
        that respond differently per query parameter.
        """
        self._responses[url] = (status, dict(headers or {}), body)

    async def _lookup(self, method: str, url: str, kwargs: dict[str, Any]) -> Any:
        self.requests.append({"method": method, "url": url, "kwargs": kwargs})
        status, headers, body = self._responses.get(url, (404, {}, None))
        if callable(body):
            status, headers, body = body(method, url, kwargs)
        return status, headers, body

    async def get(self, url: str, **kwargs: Any) -> bytes:
        status, _headers, body = await self._lookup("GET", url, kwargs)
        if status >= 400:
            raise HttpError(status, url)
        if body is None:
            return b""
        return body.encode() if isinstance(body, str) else bytes(body)

    async def get_text(self, url: str, **kwargs: Any) -> str:
        status, _headers, body = await self._lookup("GET", url, kwargs)
        if status >= 400:
            raise HttpError(status, url)
        if body is None:
            return ""
        return body.decode() if isinstance(body, bytes) else str(body)

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        status, _headers, body = await self._lookup("GET", url, kwargs)
        if status >= 400:
            raise HttpError(status, url)
        return body

    async def fetch(self, url: str, **kwargs: Any) -> HttpResponse:
        status, headers, body = await self._lookup("GET", url, kwargs)
        if body is None:
            raw = b""
        elif isinstance(body, bytes):
            raw = body
        elif isinstance(body, str):
            raw = body.encode()
        else:
            raw = str(body).encode()
        return HttpResponse(
            status=status,
            headers=headers,
            body=raw,
            url=url,
            redirects=0,
        )

    async def aclose(self) -> None:
        self.aclosed = True


def make_module_config(
    path: Path, *, key: str = "hibp", secret: str | None = None
) -> Config:
    """Build a tmp-backed config with an optional ``api_keys.<key>`` entry.

    Secrets must never be hardcoded.  When ``secret`` is omitted it falls
    back to the ``<KEY>_API_KEY`` environment variable (which a ``.env``
    file feeds via :func:`core.config.load_env_file`); with no value the
    key is left unset.
    """
    cfg = Config(path, use_env=False)
    if secret is None:
        secret = os.environ.get(f"{key.upper()}_API_KEY")
    if secret:
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
