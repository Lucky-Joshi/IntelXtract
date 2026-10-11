# Performance (Phase 25)

Scans should be fast, polite, and resilient. This document records the Phase
25 performance work, its configuration knobs, and reproducible baseline
numbers.

## Benchmarks

`scripts/bench.py` measures three axes offline (no external network):

| Section  | What it measures                                      |
|----------|-------------------------------------------------------|
| `cache`  | `AsyncTTLCache` set + hit-`get` throughput (ops/s) and hit rate |
| `engine` | Full scans across 8 trivial collectors (scans/s)      |
| `offload`| Blocking callables dispatched to a bounded 4-thread pool (ops/s) |

Run it on demand:

```console
python scripts/bench.py             # human-readable (full suite)
python scripts/bench.py --quick     # reduced iterations
python scripts/bench.py --json      # machine-readable results
```

### Baseline

Recorded 2026-10-11 on the reference workstation (Linux, Python 3.14) with
`python scripts/bench.py --json`:

```json
{
  "cache":   { "ops_per_second": 2550909, "hit_rate": 1.00 },
  "engine":  { "scans_per_second": 7414,  "modules_per_scan": 8.0 },
  "offload": { "ops_per_second": 15344,   "workers": 4.0 }
}
```

Absolute numbers vary by machine; treat them as comparable-on-one-host
throughput indicators, and re-baseline (not the figures themselves) whenever
the ratios look different.

## What was built

- **Connection pooling (S25.1)** — `HttpClient` owns one keep-alive
  `aiohttp.TCPConnector` per client (created lazily on first use) with total
  and per-host connection caps and a DNS cache, closed on `aclose()`.
  `network.pool_limit` / `network.pool_limit_per_host`.
- **Cache integration (S25.2)** — `ScanEngine` hands its shared
  `AsyncTTLCache` to the HTTP client, which stores responses that carry an
  `ETag` / `Last-Modified` and revalidates with `If-None-Match` /
  `If-Modified-Since`, serving the cached body on `304` (`fetch`, `request`,
  and `get_json`; disabled by `network.http_cache=false`). Modules get
  `ModuleContext.cached(key, factory)` for get-or-compute result caching with
  the same cache and TTL.
- **Retry logic (S25.3)** — exponential backoff with equal jitter, capped at
  `network.backoff_max`, replacing the old linear `0.5 * (attempt + 1)`.
  Only idempotent methods (GET/HEAD/OPTIONS/PUT/DELETE) retry on 408/429/5xx;
  transient network errors are always retried within the bounded attempt
  budget (`network.retries`).
- **Offloading (S25.4)** — `core/offload.py` provides `OffloadPool` (bounded
  `ThreadPoolExecutor`), a process-wide `offload()` helper, and a per-scan
  pool wired into `ModuleContext.to_thread()`. The metadata extractors (PDF /
  EXIF / OOXML) and the username site-registry load now run off the event
  loop. `performance.offload_workers` bounds the per-scan pool. A slow-task
  probe test asserts the loop stays responsive while work runs.
- **Concurrency policy (S25.5)** — a global in-flight semaphore
  (`network.max_concurrency`) plus per-host semaphores
  (`network.max_per_host`) bound simultaneous requests; `network.rate_limit`
  paces globally and `network.rate_limit_per_host` paces per provider host
  (each API provider is a distinct host, i.e. token bucket).

## Concurrency model

- No unboundedness: connection limits, concurrency caps, pacing intervals,
  and the offload thread count are all finite and configurable.
- Ordering is deadlock-free: every request acquires the global slot before
  the per-host slot, then the low-level session call.
- Semaphores are per-`HttpClient` (per scan), so parallel scans do not share
  or exhaust each other's budgets.

## Configuration reference

| Key                                   | Default | Meaning                                      |
|---------------------------------------|---------|----------------------------------------------|
| `network.pool_limit`                  | 100     | Max open connections on the shared connector |
| `network.pool_limit_per_host`         | 8       | Max connections to one host                  |
| `network.max_concurrency`             | 16      | Global in-flight request cap (0 = off)       |
| `network.max_per_host`                | 4       | Per-host in-flight cap (0 = off)             |
| `network.rate_limit`                  | 0       | Global requests/sec (0 = off)                |
| `network.rate_limit_per_host`         | 0       | Per-provider-host requests/sec (0 = off)     |
| `network.backoff_base`                | 0.5     | First retry delay (s), doubles each attempt  |
| `network.backoff_max`                 | 30      | Upper bound on a single retry delay (s)      |
| `network.http_cache`                  | true    | ETag/If-None-Match response caching          |
| `performance.offload_workers`         | 4       | Bounded per-scan offload thread pool         |
| `cache.ttl` / `cache.max_size`        | 300 / 1024 | Module + HTTP cache expiry and size      |

## Verification

- `tests/core/test_offload.py` — worker-thread execution, bounded concurrency,
  loop-responsiveness probe, shared pool lifecycle.
- `tests/modules/test_http_client.py` — connector build, backoff bounds and
  growth, idempotency gating, global/per-host concurrency caps, per-host
  pacing, and `304` cache serving for `fetch`/`get_json`.
- `tests/core/test_engine.py` — per-scan offload pool + `ModuleContext.cached`.
- `tests/modules/metadata/test_metadata_module.py` and
  `tests/modules/username/test_username_offload.py` — blocking extraction /
  registry loads run off the event-loop thread.
- `tests/test_bench.py` — benchmark script smoke tests (importable, quick
  suite, JSON output).