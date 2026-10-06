"""Async in-memory TTL cache with LRU eviction.

Single-event-loop usage (asyncio); not thread-safe.  Keys are strings — build
them with :func:`make_key`.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

DEFAULT_TTL = 300.0
DEFAULT_MAX_SIZE = 1024


def make_key(*parts: Any) -> str:
    """Build a stable cache key from arbitrary parts."""
    return ":".join(str(p) for p in parts)


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float


@dataclass(slots=True)
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0


class AsyncTTLCache:
    """LRU cache where each key expires after its own TTL."""

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        default_ttl: float = DEFAULT_TTL,
        *,
        clock: Any = time.monotonic,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._stats = CacheStats()

    async def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key``, or ``default`` when missing/expired."""
        entry = self._entries.get(key)
        if entry is None:
            self._stats.misses += 1
            return default
        if entry.expires_at <= self._clock():
            del self._entries[key]
            self._stats.expirations += 1
            self._stats.misses += 1
            return default
        self._entries.move_to_end(key)
        self._stats.hits += 1
        return entry.value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Insert or update ``key`` with an optional per-key TTL."""
        lifetime = self._default_ttl if ttl is None else ttl
        if lifetime <= 0:
            raise ValueError("ttl must be > 0")
        if key in self._entries:
            self._entries.move_to_end(key)
        elif len(self._entries) >= self._max_size:
            self._entries.popitem(last=False)
            self._stats.evictions += 1
        self._entries[key] = _Entry(value=value, expires_at=self._clock() + lifetime)

    async def delete(self, key: str) -> bool:
        """Remove ``key``; returns whether it existed."""
        return self._entries.pop(key, None) is not None

    async def clear(self) -> None:
        """Drop all entries."""
        self._entries.clear()

    async def prune(self) -> int:
        """Remove all expired entries; returns how many were dropped."""
        now = self._clock()
        expired = [k for k, e in self._entries.items() if e.expires_at <= now]
        for key in expired:
            del self._entries[key]
        self._stats.expirations += len(expired)
        return len(expired)

    def __contains__(self, key: str) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False
        if entry.expires_at <= self._clock():
            del self._entries[key]
            self._stats.expirations += 1
            return False
        return True

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def stats(self) -> CacheStats:
        """Snapshot of hit/miss/eviction counters."""
        return CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            evictions=self._stats.evictions,
            expirations=self._stats.expirations,
        )
