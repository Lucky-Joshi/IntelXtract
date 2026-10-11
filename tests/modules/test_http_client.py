"""Tests for core.http_client.HTTP facade (uses a scripted fake session)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from core.cache import AsyncTTLCache
from core.http_client import HttpClient


class _StatusError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


class FakeResponse:
    """aiohttp-like response returned by the scripted session."""

    def __init__(
        self,
        status: int = 200,
        body: bytes = b"",
        json_payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        url: str = "",
        history: list[Any] | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.json_payload = json_payload
        self.headers = dict(headers or {})
        self.url = url
        self.history = list(history or [])
        self.closed = False

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        self.closed = True
        return False

    async def read(self) -> bytes:
        return self.body

    async def json(self, content_type: Any = None) -> Any:
        return self.json_payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise _StatusError(self.status)


class ScriptedSession:
    """Replays a step list; an entry may be a response or an exception to raise.

    ``request``/``get`` are synchronous like aiohttp's ``_RequestContextManager``
    production, so ``async with session.request(...) as resp`` (used by
    :class:`HttpClient`) works indistinguishably.
    """

    def __init__(self, steps: list[Any]) -> None:
        self.steps = steps
        self.calls = 0
        self.closed = False
        self.last_kwargs: dict[str, Any] = {}

    def _next(self) -> Any:
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        return step

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        step = self._next()
        if isinstance(step, BaseException):
            raise step
        return step

    def get(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs)

    async def close(self) -> None:
        self.closed = True


class _SlowContext:
    """Async context manager that holds a slot open for a short while."""

    def __init__(self, session: _SlowSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeResponse:
        self._session.active += 1
        self._session.peak = max(self._session.peak, self._session.active)
        await asyncio.sleep(0.02)
        return FakeResponse(200, b"ok")

    async def __aexit__(self, *exc_info: Any) -> bool:
        self._session.active -= 1
        return False


class _SlowSession:
    """Session that records peak concurrent in-flight requests."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> _SlowContext:
        return _SlowContext(self)

    def get(self, url: str, **kwargs: Any) -> _SlowContext:
        return self.request("GET", url, **kwargs)

    async def close(self) -> None:
        self.closed = True


async def test_get_returns_body() -> None:
    client = HttpClient(
        retries=0, session=ScriptedSession([FakeResponse(200, b"data")])
    )
    assert await client.get("https://example.test/x") == b"data"
    assert client.metrics.requests == 1
    assert client.metrics.retries == 0


async def test_get_text_decodes_body() -> None:
    client = HttpClient(
        retries=0, session=ScriptedSession([FakeResponse(200, "héllo".encode())])
    )
    assert await client.get_text("https://example.test/") == "héllo"


async def test_get_json_decodes_payload() -> None:
    client = HttpClient(
        retries=0,
        session=ScriptedSession([FakeResponse(200, b"{}", {"a": 1})]),
    )
    assert await client.get_json("https://example.test/api") == {"a": 1}


async def test_retries_transient_errors_then_succeeds() -> None:
    scripted = ScriptedSession(
        [
            TimeoutError(),
            TimeoutError(),
            FakeResponse(200, b"ok"),
        ]
    )
    client = HttpClient(retries=2, session=scripted)
    assert await client.get("https://example.test/x") == b"ok"
    assert client.metrics.requests == 3
    assert client.metrics.retries == 2
    assert client.metrics.failures == 0
    assert scripted.calls == 3


async def test_gives_up_after_retries() -> None:
    client = HttpClient(
        retries=2,
        session=ScriptedSession([TimeoutError(), TimeoutError(), TimeoutError()]),
    )
    with pytest.raises(TimeoutError):
        await client.get("https://example.test/x")
    assert client.metrics.failures == 1


async def test_retries_server_error_then_succeeds() -> None:
    client = HttpClient(
        retries=2,
        session=ScriptedSession([FakeResponse(503, b""), FakeResponse(200, b"ok")]),
    )
    assert await client.get("https://example.test/x") == b"ok"
    assert client.metrics.retries == 1


async def test_final_server_error_raises() -> None:
    client = HttpClient(retries=0, session=ScriptedSession([FakeResponse(500, b"")]))
    with pytest.raises(_StatusError):
        await client.get("https://example.test/x")


async def test_fetch_returns_response_without_raising() -> None:
    client = HttpClient(
        retries=0,
        session=ScriptedSession(
            [
                FakeResponse(
                    404,
                    b"nope",
                    headers={"content-type": "text/plain"},
                    url="https://example.test/robots.txt",
                )
            ]
        ),
    )
    resp = await client.fetch("https://example.test/robots.txt")
    assert resp.status == 404
    assert resp.headers == {"content-type": "text/plain"}
    assert resp.text == "nope"
    assert resp.url == "https://example.test/robots.txt"
    assert resp.redirects == 0


async def test_fetch_counts_redirects() -> None:
    client = HttpClient(
        retries=0,
        session=ScriptedSession(
            [FakeResponse(200, b"final", history=[object(), object()])]
        ),
    )
    resp = await client.fetch("https://example.test/")
    assert resp.status == 200
    assert resp.redirects == 2


async def test_fetch_retries_server_error_then_returns() -> None:
    client = HttpClient(
        retries=1,
        session=ScriptedSession([FakeResponse(503, b""), FakeResponse(200, b"ok")]),
    )
    resp = await client.fetch("https://example.test/api")
    assert resp.status == 200
    assert resp.body == b"ok"
    assert client.metrics.retries == 1


async def test_fetch_returns_final_server_error_response() -> None:
    client = HttpClient(retries=0, session=ScriptedSession([FakeResponse(500, b"")]))
    resp = await client.fetch("https://example.test/api")
    assert resp.status == 500


async def test_fetch_gives_up_after_network_errors() -> None:
    client = HttpClient(
        retries=1,
        session=ScriptedSession([TimeoutError(), TimeoutError()]),
    )
    with pytest.raises(TimeoutError):
        await client.fetch("https://example.test/x")
    assert client.metrics.failures == 1


async def test_aclose_closes_session_once() -> None:
    session = ScriptedSession([])
    client = HttpClient(retries=0, session=session)
    await client.aclose()
    await client.aclose()
    assert session.closed is True
    assert client._session is None


async def test_proxy_passed_to_session() -> None:
    session = ScriptedSession([FakeResponse(200, b"ok")])
    client = HttpClient(retries=0, proxy="http://proxy.local:8080", session=session)
    await client.get("https://example.test/x")
    assert session.last_kwargs["proxy"] == "http://proxy.local:8080"


async def test_no_proxy_kwarg_when_unset() -> None:
    session = ScriptedSession([FakeResponse(200, b"ok")])
    client = HttpClient(retries=0, session=session)
    await client.get("https://example.test/x")
    assert "proxy" not in session.last_kwargs


def test_config_supplies_network_settings(tmp_path: Any) -> None:
    from core.config import Config

    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("network.timeout", 12.5)
    cfg.set("network.retries", 4)
    cfg.set("network.proxy", "http://proxy.local:3128")
    cfg.set("network.rate_limit", 25.0)

    client = HttpClient(config=cfg, session=ScriptedSession([]))
    assert client.timeout == 12.5
    assert client.retries == 4
    assert client.proxy == "http://proxy.local:3128"
    assert client.rate_limit == 25.0


async def test_rate_limit_paces_requests() -> None:
    client = HttpClient(
        retries=0,
        rate_limit=50.0,
        session=ScriptedSession([FakeResponse(200, b"a")] * 3),
    )
    start = time.monotonic()
    await client.get("https://example.test/1")
    await client.get("https://example.test/2")
    await client.get("https://example.test/3")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.03


def test_config_supplies_pooling_and_backoff(tmp_path: Any) -> None:
    from core.config import Config

    cfg = Config(tmp_path / "settings.json", use_env=False)
    cfg.set("network.pool_limit", 42)
    cfg.set("network.pool_limit_per_host", 5)
    cfg.set("network.max_concurrency", 7)
    cfg.set("network.max_per_host", 3)
    cfg.set("network.rate_limit_per_host", 9.0)
    cfg.set("network.backoff_base", 2.0)
    cfg.set("network.backoff_max", 20.0)
    cfg.set("network.http_cache", False)

    client = HttpClient(config=cfg, session=ScriptedSession([]))
    assert client.pool_limit == 42
    assert client.pool_limit_per_host == 5
    assert client.max_concurrency == 7
    assert client.max_per_host == 3
    assert client.rate_limit_per_host == 9.0
    assert client.backoff_base == 2.0
    assert client.backoff_max == 20.0
    assert client._http_cache is False


async def test_ensure_session_builds_bounded_connector() -> None:
    client = HttpClient(retries=0, pool_limit=33, pool_limit_per_host=4)
    await client._ensure_session()
    assert client._connector is not None
    assert client._connector.limit == 33
    await client.aclose()
    assert client._connector is None


def test_backoff_zero_base_disables() -> None:
    client = HttpClient(backoff_base=0.0, session=ScriptedSession([]))
    assert client._backoff_delay(5) == 0.0


def test_backoff_is_capped_at_max() -> None:
    client = HttpClient(backoff_base=1.0, backoff_max=2.0, session=ScriptedSession([]))
    for attempt in range(10):
        assert 0.0 <= client._backoff_delay(attempt) <= 2.0


async def test_backoff_grows_exponentially_with_jitter() -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    client = HttpClient(
        retries=4,
        backoff_base=1.0,
        backoff_max=8.0,
        sleep=fake_sleep,
        session=ScriptedSession([TimeoutError()] * 5),
    )
    with pytest.raises(TimeoutError):
        await client.get("https://example.test/x")

    assert len(delays) == 4
    bounds = [(0.5, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 8.0)]
    for delay, (low, high) in zip(delays, bounds, strict=True):
        assert low <= delay <= high


async def test_non_idempotent_request_not_retried_on_status() -> None:
    session = ScriptedSession([FakeResponse(503, b"")])
    client = HttpClient(retries=3, session=session)
    resp = await client.request("POST", "https://example.test/x")
    assert resp.status == 503
    assert session.calls == 1
    assert client.metrics.retries == 0


async def test_global_concurrency_cap() -> None:
    session = _SlowSession()
    client = HttpClient(retries=0, max_concurrency=2, max_per_host=0, session=session)
    await asyncio.gather(*(client.fetch(f"https://example.test/{i}") for i in range(6)))
    assert session.peak == 2
    assert session.active == 0


async def test_per_host_concurrency_cap() -> None:
    session = _SlowSession()
    client = HttpClient(retries=0, max_concurrency=0, max_per_host=2, session=session)
    await asyncio.gather(*(client.fetch(f"https://example.test/{i}") for i in range(6)))
    assert session.peak == 2
    assert session.active == 0


async def test_per_host_rate_limit_paces() -> None:
    client = HttpClient(
        retries=0,
        rate_limit_per_host=50.0,
        session=ScriptedSession([FakeResponse(200, b"a")] * 3),
    )
    start = time.monotonic()
    await client.get("https://example.test/1")
    await client.get("https://example.test/2")
    await client.get("https://example.test/3")
    assert time.monotonic() - start >= 0.03


async def test_fetch_serves_cached_body_on_304() -> None:
    cache = AsyncTTLCache(max_size=8, default_ttl=60.0)
    session = ScriptedSession(
        [
            FakeResponse(200, b"payload", headers={"ETag": "v1"}),
            FakeResponse(304, b""),
        ]
    )
    client = HttpClient(retries=0, session=session, cache=cache)

    first = await client.fetch("https://example.test/x")
    assert first.body == b"payload"

    second = await client.fetch("https://example.test/x")
    assert second.status == 200
    assert second.body == b"payload"
    assert client.metrics.cache_hits == 1
    assert session.calls == 2
    assert session.last_kwargs["headers"]["If-None-Match"] == "v1"


async def test_fetch_without_validator_not_cached() -> None:
    cache = AsyncTTLCache(max_size=8, default_ttl=60.0)
    session = ScriptedSession([FakeResponse(200, b"a"), FakeResponse(200, b"a")])
    client = HttpClient(retries=0, session=session, cache=cache)
    await client.fetch("https://example.test/x")
    await client.fetch("https://example.test/x")
    assert client.metrics.cache_hits == 0
    assert session.calls == 2


async def test_http_cache_can_be_disabled() -> None:
    cache = AsyncTTLCache(max_size=8, default_ttl=60.0)
    session = ScriptedSession(
        [
            FakeResponse(200, b"a", headers={"ETag": "v1"}),
            FakeResponse(200, b"a", headers={"ETag": "v1"}),
        ]
    )
    client = HttpClient(retries=0, http_cache=False, session=session, cache=cache)
    await client.fetch("https://example.test/x")
    await client.fetch("https://example.test/x")
    assert client.metrics.cache_hits == 0
    assert session.calls == 2


async def test_get_json_serves_cached_payload_on_304() -> None:
    cache = AsyncTTLCache(max_size=8, default_ttl=60.0)
    session = ScriptedSession(
        [
            FakeResponse(200, b"{}", {"a": 1}, headers={"ETag": "v1"}),
            FakeResponse(304, b""),
        ]
    )
    client = HttpClient(retries=0, session=session, cache=cache)
    assert await client.get_json("https://example.test/api") == {"a": 1}
    assert await client.get_json("https://example.test/api") == {"a": 1}
    assert client.metrics.cache_hits == 1
    assert session.calls == 2
