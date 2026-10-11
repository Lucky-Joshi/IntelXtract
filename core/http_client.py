"""Async HTTP client for modules.

Wraps a lazily-created ``aiohttp`` session (never touches the network until
the first request) so engines and scans that never make HTTP calls don't pay
for a connection pool or leak a session.  ``get_json``/``get_text``/
``get_bytes`` retry transient network errors and 429/5xx responses by default.

Phase 25 adds a shared keep-alive connection pool (``network.pool_limit``/
``pool_limit_per_host``), global/per-host concurrency caps, per-host pacing,
exponential-backoff-with-jitter retries, and conditional-request caching
(``If-None-Match``/``If-Modified-Since``) backed by an injected
:class:`~core.cache.AsyncTTLCache`.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from core.cache import AsyncTTLCache
from core.config import Config
from core.logger import get_logger

DEFAULT_USER_AGENT = "IntelXtract/0.1 (+https://github.com/anomalyco/IntelXtract)"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
DEFAULT_POOL_LIMIT = 100
DEFAULT_POOL_LIMIT_PER_HOST = 8
DEFAULT_MAX_CONCURRENCY = 16
DEFAULT_MAX_PER_HOST = 4
DEFAULT_BACKOFF_BASE = 0.5
DEFAULT_BACKOFF_MAX = 30.0
RETRYABLE_NETWORK_ERRORS: tuple[type[Exception], ...] = (
    aiohttp.ClientConnectorError,
    asyncio.TimeoutError,
)
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

_log = get_logger(__name__)


@dataclass(slots=True)
class ClientMetrics:
    """Request counters exposed to modules and the UI."""

    requests: int = 0
    retries: int = 0
    failures: int = 0
    cache_hits: int = 0


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


@dataclass(slots=True)
class _CachedJson:
    """Cached decoded JSON payload plus its validators for conditional GETs."""

    payload: Any
    headers: dict[str, str]


def _host_of(url: str) -> str:
    """Best-effort hostname extraction for per-host bucketing."""
    host = urlsplit(url).hostname
    return host or url


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup."""
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _cache_key(method: str, url: str, params: Mapping[str, Any] | None) -> str:
    """Stable cache key for a GET request URL and its query params."""
    if params:
        query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    else:
        query = ""
    return f"http:{method.upper()}:{url}?{query}"


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
        rate_limit_per_host: float | None = None,
        backoff_base: float | None = None,
        backoff_max: float | None = None,
        pool_limit: int | None = None,
        pool_limit_per_host: int | None = None,
        max_concurrency: int | None = None,
        max_per_host: int | None = None,
        http_cache: bool | None = None,
        cache: AsyncTTLCache | None = None,
        sleep: Any = None,
        session: Any = None,
    ) -> None:
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.retries = retries if retries is not None else DEFAULT_RETRIES
        self.proxy = proxy or ""
        self.rate_limit = rate_limit if rate_limit is not None else 0.0
        self.rate_limit_per_host = (
            rate_limit_per_host if rate_limit_per_host is not None else 0.0
        )
        self.backoff_base = (
            backoff_base if backoff_base is not None else DEFAULT_BACKOFF_BASE
        )
        self.backoff_max = (
            backoff_max if backoff_max is not None else DEFAULT_BACKOFF_MAX
        )
        self.pool_limit = pool_limit if pool_limit is not None else DEFAULT_POOL_LIMIT
        self.pool_limit_per_host = (
            pool_limit_per_host
            if pool_limit_per_host is not None
            else DEFAULT_POOL_LIMIT_PER_HOST
        )
        self.max_concurrency = (
            max_concurrency if max_concurrency is not None else DEFAULT_MAX_CONCURRENCY
        )
        self.max_per_host = (
            max_per_host if max_per_host is not None else DEFAULT_MAX_PER_HOST
        )
        self._http_cache = True if http_cache is None else http_cache

        if config is not None:
            self.timeout = float(
                config.get("network.timeout", config.get("http.timeout", self.timeout))
            )
            self.retries = int(
                config.get("network.retries", config.get("http.retries", self.retries))
            )
            self.proxy = self.proxy or str(config.get("network.proxy", "") or "")
            self.rate_limit = float(config.get("network.rate_limit", self.rate_limit))
            self.rate_limit_per_host = float(
                config.get("network.rate_limit_per_host", self.rate_limit_per_host)
            )
            self.backoff_base = float(
                config.get("network.backoff_base", self.backoff_base)
            )
            self.backoff_max = float(
                config.get("network.backoff_max", self.backoff_max)
            )
            self.pool_limit = int(config.get("network.pool_limit", self.pool_limit))
            self.pool_limit_per_host = int(
                config.get("network.pool_limit_per_host", self.pool_limit_per_host)
            )
            self.max_concurrency = int(
                config.get("network.max_concurrency", self.max_concurrency)
            )
            self.max_per_host = int(
                config.get("network.max_per_host", self.max_per_host)
            )
            self._http_cache = bool(config.get("network.http_cache", self._http_cache))

        self._user_agent = user_agent or DEFAULT_USER_AGENT
        self._headers = dict(headers or {})
        self._session = session
        self._connector: aiohttp.TCPConnector | None = None
        self._cache = cache
        self._sleep = sleep or asyncio.sleep
        self.metrics = ClientMetrics()
        self._throttle_lock = asyncio.Lock()
        self._last_slot: dict[str, float] = {}
        self._semaphore = (
            asyncio.Semaphore(max(self.max_concurrency, 1))
            if self.max_concurrency > 0
            else None
        )
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}

    def _proxy_kwargs(self) -> dict[str, Any]:
        return {"proxy": self.proxy} if self.proxy else {}

    @property
    def _cache_active(self) -> bool:
        """True when conditional-request caching should be attempted."""
        return self._http_cache and self._cache is not None and self._cache.enabled

    async def _pace(self, key: str, interval: float) -> None:
        """Serialized minimum-interval pacing for one throttle bucket."""
        async with self._throttle_lock:
            now = time.monotonic()
            delay = self._last_slot.get(key, 0.0) + interval - now
            if delay > 0:
                await self._sleep(delay)
            self._last_slot[key] = time.monotonic()

    async def _throttle(self, url: str | None = None) -> None:
        """Enforce ``network.rate_limit`` and ``rate_limit_per_host`` (0 disables)."""
        if self.rate_limit > 0:
            await self._pace("", 1.0 / self.rate_limit)
        if self.rate_limit_per_host > 0 and url is not None:
            await self._pace(_host_of(url), 1.0 / self.rate_limit_per_host)

    def _host_semaphore(self, url: str) -> asyncio.Semaphore | None:
        """Lazily build the per-host concurrency gate for ``url``."""
        if self.max_per_host <= 0:
            return None
        host = _host_of(url)
        semaphore = self._host_semaphores.get(host)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.max_per_host)
            self._host_semaphores[host] = semaphore
        return semaphore

    @asynccontextmanager
    async def _acquire(self, url: str) -> AsyncIterator[None]:
        """Hold the global and per-host in-flight slots for one request."""
        host_semaphore = self._host_semaphore(url)
        acquired_global = False
        acquired_host = False
        try:
            if self._semaphore is not None:
                await self._semaphore.acquire()
                acquired_global = True
            if host_semaphore is not None:
                await host_semaphore.acquire()
                acquired_host = True
            yield
        finally:
            if acquired_host and host_semaphore is not None:
                host_semaphore.release()
            if acquired_global and self._semaphore is not None:
                self._semaphore.release()

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with equal jitter, capped at ``backoff_max``."""
        if self.backoff_base <= 0:
            return 0.0
        ceiling: float = min(self.backoff_base * (2**attempt), self.backoff_max)
        jitter: float = float(random.uniform(0.0, ceiling / 2))  # noqa: S311
        return ceiling / 2 + jitter

    def _conditional_headers(
        self, headers: Mapping[str, str], stored_headers: Mapping[str, str]
    ) -> dict[str, str]:
        """Add ``If-None-Match``/``If-Modified-Since`` from a cached response."""
        merged = dict(headers)
        if etag := _header(stored_headers, "etag"):
            merged.setdefault("If-None-Match", etag)
        if modified := _header(stored_headers, "last-modified"):
            merged.setdefault("If-Modified-Since", modified)
        return merged

    @property
    def closed(self) -> bool:
        """True when the underlying session is closed or absent."""
        return self._session is None or self._session.closed

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=self.pool_limit,
                limit_per_host=self.pool_limit_per_host,
                ttl_dns_cache=300,
            )
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": self._user_agent, **self._headers},
                connector=self._connector,
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
        """GET a URL and decode the response as JSON (conditional-cache aware)."""
        session = await self._ensure_session()
        headers = kwargs.pop("headers", None)
        params = kwargs.pop("params", None)

        cache_key: str | None = None
        cached: _CachedJson | None = None
        request_headers = dict(headers or {})
        if self._cache_active:
            cache_key = _cache_key("GET", url, params)
            stored = await self._cache.get(cache_key)  # type: ignore[union-attr]
            if isinstance(stored, _CachedJson):
                cached = stored
                request_headers = self._conditional_headers(
                    request_headers, stored.headers
                )

        await self._throttle(url)
        call_kwargs: dict[str, Any] = {**kwargs, **self._proxy_kwargs()}
        async with self._acquire(url):
            async with session.get(
                url,
                headers=request_headers or None,
                params=params,
                **call_kwargs,
            ) as resp:
                if resp.status == 304 and cached is not None:
                    self.metrics.cache_hits += 1
                    return cached.payload
                resp.raise_for_status()
                payload = await resp.json(content_type=None)
                if cache_key is not None:
                    await self._cache.set(  # type: ignore[union-attr]
                        cache_key, _CachedJson(payload, dict(resp.headers))
                    )
                return payload

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
        await self._throttle(url)
        proxy_kwargs = self._proxy_kwargs()
        try:
            async with self._acquire(url):
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
        attach extra ``headers`` (e.g. API keys).  Only idempotent methods are
        retried on retryable statuses.  GETs participate in conditional caching.
        """
        session = await self._ensure_session()
        normalized = method.upper()
        retryable = normalized in _IDEMPOTENT_METHODS

        cache_key: str | None = None
        cached: HttpResponse | None = None
        request_headers = dict(headers or {})
        if normalized == "GET" and self._cache_active:
            cache_key = _cache_key(normalized, url, params)
            stored = await self._cache.get(cache_key)  # type: ignore[union-attr]
            if isinstance(stored, HttpResponse):
                cached = stored
                request_headers = self._conditional_headers(
                    request_headers, stored.headers
                )

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            should_raise = attempt >= self.retries
            self.metrics.requests += 1
            await self._throttle(url)
            proxy_kwargs = self._proxy_kwargs()
            try:
                async with self._acquire(url):
                    async with session.request(
                        normalized,
                        url,
                        params=params,
                        headers=request_headers or None,
                        allow_redirects=allow_redirects,
                        **proxy_kwargs,
                    ) as resp:
                        if resp.status == 304 and cached is not None:
                            self.metrics.cache_hits += 1
                            return cached
                        if retryable and (
                            resp.status in (408, 429) or resp.status >= 500
                        ):
                            if not should_raise:
                                self.metrics.retries += 1
                                await self._sleep(self._backoff_delay(attempt))
                                continue
                        response = HttpResponse(
                            status=resp.status,
                            headers=dict(resp.headers),
                            url=str(resp.url),
                            redirects=len(resp.history),
                            body=await resp.read(),
                        )
                        if cache_key is not None and response.status == 200:
                            if _header(response.headers, "etag") or _header(
                                response.headers, "last-modified"
                            ):
                                await self._cache.set(  # type: ignore[union-attr]
                                    cache_key, response
                                )
                        return response
            except RETRYABLE_NETWORK_ERRORS as exc:
                last_error = exc
                if should_raise:
                    self.metrics.failures += 1
                    raise
                self.metrics.retries += 1
                await self._sleep(self._backoff_delay(attempt))
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
            await self._throttle(url)
            call_kwargs: dict[str, Any] = {**kwargs, **self._proxy_kwargs()}
            try:
                async with self._acquire(url):
                    async with session.request(method, url, **call_kwargs) as resp:
                        if resp.status in (408, 429) or resp.status >= 500:
                            if should_raise:
                                resp.raise_for_status()
                            self.metrics.retries += 1
                            await self._sleep(self._backoff_delay(attempt))
                            continue
                        resp.raise_for_status()
                        return await resp.read()
            except RETRYABLE_NETWORK_ERRORS as exc:
                last_error = exc
                if should_raise:
                    self.metrics.failures += 1
                    raise
                self.metrics.retries += 1
                await self._sleep(self._backoff_delay(attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"request to {url!r} exhausted retries")

    async def aclose(self) -> None:
        """Close the underlying session (no-op when it was never opened)."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        if self._connector is not None:
            await self._connector.close()
            self._connector = None
