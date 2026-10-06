"""Async TTL cache tests (fake clock, no timing flakiness)."""

import pytest

from core.cache import AsyncTTLCache, make_key


class FakeClock:
    """Mutable monotonic clock."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _cache(max_size: int = 4, ttl: float = 10.0) -> tuple[AsyncTTLCache, FakeClock]:
    clock = FakeClock()
    return AsyncTTLCache(max_size=max_size, default_ttl=ttl, clock=clock), clock


async def test_set_get_roundtrip() -> None:
    cache, _ = _cache()
    await cache.set("a", 1)
    assert await cache.get("a") == 1
    assert await cache.get("missing", "fallback") == "fallback"


async def test_ttl_expiry() -> None:
    cache, clock = _cache(ttl=5.0)
    await cache.set("a", "value")
    clock.advance(4.9)
    assert await cache.get("a") == "value"
    clock.advance(0.2)
    assert await cache.get("a") is None
    assert "a" not in cache
    assert cache.stats.expirations >= 1


async def test_per_key_ttl() -> None:
    cache, clock = _cache(ttl=10.0)
    await cache.set("short", 1, ttl=1.0)
    await cache.set("long", 2, ttl=100.0)
    clock.advance(2.0)
    assert await cache.get("short") is None
    assert await cache.get("long") == 2


async def test_lru_eviction() -> None:
    cache, _ = _cache(max_size=2)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)
    assert await cache.get("a") is None
    assert await cache.get("b") == 2
    assert await cache.get("c") == 3
    assert cache.stats.evictions == 1


async def test_hit_refreshes_lru_order() -> None:
    cache, _ = _cache(max_size=2)
    await cache.set("a", 1)
    await cache.set("b", 2)
    assert await cache.get("a") == 1  # a becomes most-recent
    await cache.set("c", 3)  # evicts b
    assert await cache.get("b") is None
    assert await cache.get("a") == 1


async def test_delete_clear_prune() -> None:
    cache, clock = _cache()
    await cache.set("a", 1)
    assert await cache.delete("a") is True
    assert await cache.delete("a") is False
    await cache.set("b", 2)
    await cache.set("c", 3)
    clock.advance(50.0)
    assert await cache.prune() == 2
    assert len(cache) == 0
    await cache.set("d", 4)
    await cache.clear()
    assert len(cache) == 0


async def test_stats_counts() -> None:
    cache, _ = _cache()
    await cache.set("a", 1)
    await cache.get("a")
    await cache.get("a")
    await cache.get("nope")
    stats = cache.stats
    assert stats.hits == 2
    assert stats.misses == 1
    assert stats.evictions == 0


def test_make_key() -> None:
    assert make_key("whois", "example.com") == "whois:example.com"
    assert make_key(1, "a", None) == "1:a:None"


def test_invalid_construction() -> None:
    with pytest.raises(ValueError):
        AsyncTTLCache(max_size=0)
    with pytest.raises(ValueError):
        AsyncTTLCache(default_ttl=0)


async def test_invalid_ttl_set() -> None:
    cache, _ = _cache()
    with pytest.raises(ValueError):
        await cache.set("a", 1, ttl=0)
