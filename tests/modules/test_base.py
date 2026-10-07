"""Tests for modules.base — the Phase 7 collector contract and helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.constants import TargetType
from core.models import ModuleResult
from fakes import (
    DummyModule,
    FakeHttpClient,
    make_module_config,
    make_module_context,
)
from modules.base import BaseModule, retry, run_with_timeout


class RetryCounter:
    def __init__(self, failures: int = 2) -> None:
        self.calls = 0
        self.failures = failures

    async def attempt(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("transient")
        return "ok"


async def test_run_with_timeout_completes() -> None:
    async def fast() -> str:
        return "done"

    assert await run_with_timeout(fast(), 5.0) == "done"


async def test_run_with_timeout_raises() -> None:
    async def slow() -> None:
        await asyncio.sleep(10)

    with pytest.raises(asyncio.TimeoutError):
        await run_with_timeout(slow(), 0.01)


async def test_retry_succeeds_after_failures() -> None:
    counter = RetryCounter(failures=2)

    @retry(attempts=3, delay=0, exceptions=(RuntimeError,))
    async def wrapped() -> str:
        return await counter.attempt()

    assert await wrapped() == "ok"
    assert counter.calls == 3


async def test_retry_gives_up() -> None:
    counter = RetryCounter(failures=99)

    @retry(attempts=3, delay=0, exceptions=(RuntimeError,))
    async def wrapped() -> str:
        return await counter.attempt()

    with pytest.raises(RuntimeError, match="transient"):
        await wrapped()
    assert counter.calls == 3


async def test_retry_passes_through_unlisted_errors() -> None:
    calls = 0

    @retry(attempts=3, delay=0, exceptions=(RuntimeError,))
    async def wrapped() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await wrapped()
    assert calls == 1


async def test_dummy_module_contract(tmp_path: Path) -> None:
    module = DummyModule()
    assert module.name == "dummy"
    assert TargetType.DOMAIN in module.target_types
    assert module.requires_keys == ()
    assert module.validate("example.com")
    assert not module.validate("   ")
    assert module.parse({"a": 1}) == {"a": 1}
    exported = module.export(ModuleResult(data={"x": 1}))
    assert exported["data"] == {"x": 1}


async def test_dummy_module_runs_with_ctx(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://dummy.local/example.com", body="hello-parsed")
    ctx = make_module_context(
        make_module_config(tmp_path),
        http=client,
        extras={"dummy.http": True},
    )
    result = await DummyModule().run("example.com", ctx)
    assert isinstance(result, ModuleResult)
    assert result.data["target"] == "example.com"
    assert result.data["hits"] == 1
    assert result.findings[0].module == "dummy"
    assert result.findings[0].confidence == 0.9


async def test_dummy_module_uses_http_and_cache(tmp_path: Path) -> None:
    client = FakeHttpClient()
    client.stub("https://dummy.local/example.com", body="hello-parsed")
    ctx = make_module_context(
        make_module_config(tmp_path),
        http=client,
        extras={"dummy.http": True},
    )
    module = DummyModule()
    first = await module.run("example.com", ctx)
    second = await module.run("example.com", ctx)
    assert first.data["raw"] == "hello-parsed"
    assert first.data["hits"] == 1
    assert second.data["hits"] == 2
    assert len(client.requests) == 2


async def test_dummy_module_skips_http_without_flag(tmp_path: Path) -> None:
    client = FakeHttpClient()
    ctx = make_module_context(make_module_config(tmp_path), http=client)
    result = await DummyModule().run("example.com", ctx)
    assert "raw" not in result.data
    assert len(client.requests) == 0


async def test_http_conveniences_require_http(tmp_path: Path) -> None:
    module = DummyModule()
    ctx = make_module_context(make_module_config(tmp_path))
    with pytest.raises(RuntimeError, match=r"ctx\.http"):
        await module.http_get_text(ctx, "https://x")
    with pytest.raises(RuntimeError, match=r"ctx\.http"):
        await module.http_get_json(ctx, "https://x")


async def test_context_api_key_accessor(tmp_path: Path) -> None:
    ctx = make_module_context(make_module_config(tmp_path))
    assert ctx.api_key("hibp") == "HIBP-SECRET-1234"
    assert ctx.api_key("missing") is None


class _MissingRun(BaseModule):
    """Abstract (no run()): instantiating must fail."""

    name = "missing"


def test_abstract_run_is_enforced() -> None:
    with pytest.raises(TypeError):
        _MissingRun()  # type: ignore[abstract]
