"""Async HTTP client for modules.

Wraps a lazily-created ``aiohttp`` session (never touches the network until
the first request) so engines and scans that never make HTTP calls don't pay
for a connection pool or leak a session.  ``get_json``/``get_text``/
``get_bytes`` retry transient network errors and 429/5xx responses by
default.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp

from core.config import Config
from core.logger import get_logger

DEFAULT_USER_AGENT = "IntelXtract/0.1 (+https://github.com/anomalyco/IntelXtract)"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
RETRYABLE_NETWORK_ERRORS: tuple[type[Exception], ...] = (
    aiohttp.ClientConnectorError,
    asyncio.TimeoutError,
)

_log = get_logger(__name__)


@dataclass(slots=True)
class ClientMetrics:
    """Request counters exposed to modules and the UI."""

    requests: int = 0
    retries: int = 0
    failures: int = 0


@dataclass(slots=True)
class HttpResponse:
    """Captured HTTP response: status, headers, body, and redirect info."""

    status: int
    headers: dict[str, str]
    body: bytes = b""
    url: str = ""
    redirects: int = 0

    @property
    def text(self) -> str:
        """Body decoded as UTF-8 text."""
        return self.body.decode("utf-8", errors="replace")


class HttpClient:
    """Small HTTP facade with a shared session built on first use."""

    _session: aiohttp.ClientSession | None

    def __init__(
        self,
        *,
        config: Config | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        user_agent: str | None = None,
        headers: Mapping[str, str] | None = None,
        proxy: str | None = None,
        rate_limit: float | None = None,
        session: Any = None,
    ) -> None:
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.retries = retries if retries is not None else DEFAULT_RETRIES
        self.proxy = proxy or ""
        self.rate_limit = rate_limit if rate_limit is not None else 0.0
        if config is not None:
            self.timeout = float(
                config.get("network.timeout", config.get("http.timeout", self.timeout))
            )
            self.retries = int(
                config.get("network.retries", config.get("http.retries", self.retries))
            )
            self.proxy = self.proxy or str(config.get("network.proxy", "") or "")
            self.rate_limit = float(config.get("network.rate_limit", self.rate_limit))
        self._user_agent = user_agent or DEFAULT_USER_AGENT
        self._headers = dict(headers or {})
        self._session = session
        self.metrics = ClientMetrics()
        self._throttle_lock = asyncio.Lock()
        self._last_request = 0.0

    def _proxy_kwargs(self) -> dict[str, Any]:
        return {"proxy": self.proxy} if self.proxy else {}

    async def _throttle(self) -> None:
        """Enforce ``network.rate_limit`` requests/second (0 disables)."""
        if self.rate_limit <= 0:
            return
        interval = 1.0 / self.rate_limit
        async with self._throttle_lock:
            now = time.monotonic()
            delay = self._last_request + interval - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = time.monotonic()

    @property
    def closed(self) -> bool:
        """True when the underlying session is closed or absent."""
        return self._session is None or self._session.closed

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": self._user_agent, **self._headers},
            )
        return self._session

    async def get(
        self, url: str, *, params: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> bytes:
        """GET a URL and return the raw body (retrying transient errors)."""
        return await self._request("GET", url, params=params, **kwargs)

    async def get_text(self, url: str, **kwargs: Any) -> str:
        """GET a URL and return its text body (decoded by aiohttp)."""
        body = await self.get(url, **kwargs)
        return body.decode("utf-8", errors="replace")

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET a URL and decode the response as JSON."""
        session = await self._ensure_session()
        headers = kwargs.pop("headers", None)
        params = kwargs.pop("params", None)
        await self._throttle()
        call_kwargs: dict[str, Any] = {**kwargs, **self._proxy_kwargs()}
        async with session.get(
            url, headers=headers, params=params, **call_kwargs
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def post_json(
        self,
        url: str,
        *,
        json_body: Any,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """POST a JSON body and decode the JSON response (raises on 4xx/5xx)."""
        session = await self._ensure_session()
        self.metrics.requests += 1
        await self._throttle()
        proxy_kwargs = self._proxy_kwargs()
        try:
            async with session.post(
                url,
                json=json_body,
                headers=headers,
                params=params,
                **proxy_kwargs,
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except RETRYABLE_NETWORK_ERRORS:
            self.metrics.failures += 1
            raise

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """Send an arbitrary HTTP method and return a non-raising response.

        Behaves like :meth:`fetch` (retries 408/429/5xx and transient network
        errors, returns the final 4xx/5xx response so callers can inspect it)
        but lets modules probe methods such as ``OPTIONS`` or ``HEAD`` and
        attach extra ``headers`` (e.g. API keys).
        """
        session = await self._ensure_session()
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            should_raise = attempt >= self.retries
            self.metrics.requests += 1
            await self._throttle()
            proxy_kwargs = self._proxy_kwargs()
            try:
                async with session.request(
                    method.upper(),
                    url,
                    params=params,
                    headers=headers,
                    allow_redirects=allow_redirects,
                    **proxy_kwargs,
                ) as resp:
                    if resp.status in (408, 429) or resp.status >= 500:
                        if not should_raise:
                            self.metrics.retries += 1
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                    return HttpResponse(
                        status=resp.status,
                        headers=dict(resp.headers),
                        url=str(resp.url),
                        redirects=len(resp.history),
                        body=await resp.read(),
                    )
            except RETRYABLE_NETWORK_ERRORS as exc:
                last_error = exc
                if should_raise:
                    self.metrics.failures += 1
                    raise
                self.metrics.retries += 1
                await asyncio.sleep(0.5 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"request to {url!r} exhausted retries")

    async def fetch(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """GET a URL and return its status/headers/body without raising.

        Transient failures (408/429/5xx, timeouts, connection errors) are
        retried; the final response is returned even for 4xx/5xx so callers
        can react to status codes (e.g. a missing ``robots.txt``).  Only
        exhausted network errors bubble up.
        """
        return await self.request(
            "GET",
            url,
            params=params,
            headers=headers,
            allow_redirects=allow_redirects,
        )

    async def _request(self, method: str, url: str, **kwargs: Any) -> bytes:
        session = await self._ensure_session()
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            should_raise = attempt >= self.retries
            self.metrics.requests += 1
            await self._throttle()
            call_kwargs: dict[str, Any] = {**kwargs, **self._proxy_kwargs()}
            try:
                async with session.request(method, url, **call_kwargs) as resp:
                    if resp.status in (408, 429) or resp.status >= 500:
                        if should_raise:
                            resp.raise_for_status()
                        self.metrics.retries += 1
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    return await resp.read()
            except RETRYABLE_NETWORK_ERRORS as exc:
                last_error = exc
                if should_raise:
                    self.metrics.failures += 1
                    raise
                self.metrics.retries += 1
                await asyncio.sleep(0.5 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"request to {url!r} exhausted retries")

    async def aclose(self) -> None:
        """Close the underlying session (no-op when it was never opened)."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
