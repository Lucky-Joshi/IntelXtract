"""Tests for core.http_client.HTTP facade (uses a scripted fake session)."""

from __future__ import annotations

from typing import Any

import pytest

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

    def _next(self) -> Any:
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        return step

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        step = self._next()
        if isinstance(step, BaseException):
            raise step
        return step

    def get(self, url: str, **kwargs: Any) -> Any:
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
