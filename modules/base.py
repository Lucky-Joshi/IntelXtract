"""Uniform collector interface (Phase 7).

Every scan module subclasses :class:`BaseModule`, declares its metadata
(``name``, ``target_types``, ``requires_keys``), validates targets, and
returns a :class:`core.models.ModuleResult` from :meth:`BaseModule.run`.
Shared timeout/retry plumbing and HTTP conveniences live here so Phase 8+
collectors stay thin.
"""

from __future__ import annotations

import asyncio
import functools
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ParamSpec, TypeVar

from core.constants import TargetType
from core.engine import ModuleContext
from core.models import ModuleResult

T = TypeVar("T")
P = ParamSpec("P")

RetryableErrors = tuple[type[Exception], ...]


async def run_with_timeout[T](awaitable: Awaitable[T], timeout_seconds: float) -> T:
    """Run an awaitable under ``asyncio.wait_for``."""
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def retry(
    *,
    attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: RetryableErrors = (Exception,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator that retries an async callable on transient failures."""

    def decorator(
        fn: Callable[P, Awaitable[T]],
    ) -> Callable[P, Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    last = exc
                    if attempt >= attempts:
                        break
                    await asyncio.sleep(delay * (backoff ** (attempt - 1)))
            if last is not None:
                raise last
            raise RuntimeError("retry loop exited without a result")

        return wrapper

    return decorator


class BaseModule(ABC):
    """Abstract scan collector consumed by the engine and registry.

    Subclasses must set :attr:`name` and implement :meth:`run`;
    :attr:`target_types` limits which target kinds the module accepts and
    :attr:`requires_keys` lists the ``api_keys.*`` entries it needs.  The
    engine's planner skips modules whose keys are unconfigured.
    """

    name: str = ""
    target_types: tuple[TargetType, ...] = ()
    requires_keys: tuple[str, ...] = ()
    description: str = ""
    timeout: float | None = None
    retries: int = 0

    def validate(self, target: str) -> bool:
        """Reject obviously unusable targets; subclasses may refine."""
        return bool(target and target.strip())

    @abstractmethod
    async def run(self, target: str, ctx: ModuleContext) -> ModuleResult:
        """Execute the collector and return normalized findings."""

    def parse(self, raw: Any) -> Any:
        """Turn a raw upstream payload into the module's structured form."""
        return raw

    def export(self, result: ModuleResult) -> Mapping[str, Any]:
        """Render a result for reports/exporters (defaults to its dict form)."""
        return result.to_dict()

    async def http_get_json(self, ctx: ModuleContext, url: str, **kwargs: Any) -> Any:
        """Convenience: GET JSON through the context's shared HTTP client."""
        if ctx.http is None:
            raise RuntimeError(f"{self.name} requires ctx.http to perform requests")
        return await ctx.http.get_json(url, **kwargs)

    async def http_get_text(self, ctx: ModuleContext, url: str, **kwargs: Any) -> str:
        """Convenience: GET text through the context's shared HTTP client."""
        if ctx.http is None:
            raise RuntimeError(f"{self.name} requires ctx.http to perform requests")
        return await ctx.http.get_text(url, **kwargs)
