# Changelog

All notable changes to IntelXtract are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Phase 9 — IP module: three collectors under `modules/ip/`. `geo.py`
  resolves coarse location plus ISP/ASN/organization from the keyless
  ip-api.org endpoint and caches successful lookups in the engine cache for
  ``geo.cache_ttl`` (default 24h). `rdns.py` performs reverse DNS over
  DNS-over-HTTPS for both IPv4 (`in-addr.arpa`) and IPv6 (`ip6.arpa`) and
  re-resolves each PTR hostname for a forward-confirmed (FCrDNS) match.
  `reputation.py` probes the Spamhaus ZEN DNSBL (delisting codes
  127.0.0.2-11 classified as SBL/XBL/CSS/PBL) over DoH and, only when an
  ``abuseipdb`` API key is configured, checks AbuseIPDB report score. IPv6
  targets are reported as out-of-scope for the IPv4-only DNSBL. Every data
  source degrades to a LOW finding / ``degraded`` state instead of failing
  the scan; the quick/deep IP selection maps now list the three modules and
  the CLI/engine register them. Tests cover cached geo lookups (cache-hit
  path), forward-confirmed and mismatched reverse records, clean/listed/
  IPv6 DNSBL, keyed and keyless AbuseIPDB, offline degradation, and IPv4 +
  IPv6 deep scans persisted end-to-end into SQLite.
- Phase 10 — website module: five collectors under `modules/website/`.
  `headers.py` profiles the final response (server/X-Powered-By disclosure →
  MEDIUM, compression, six security headers present/missing, cookie flags
  Secure/HttpOnly/SameSite with insecure cookie findings by severity).
  `tech_stack.py` fingerprints CMS/frameworks/libs from headers, cookies, and
  HTML against an internal signature table (WordPress, Drupal, Joomla,
  nginx, Apache, Cloudflare, Django, Laravel, React, Vue, jQuery, Bootstrap,
  Webpack, Gatsby). `favicon.py` fingerprints `/favicon.ico` as
  FNV-1a(base64(md5(icon))) for external cross-site correlation. `robots.py`
  parses robots.txt into user-agent groups (allow/disallow/crawl-delay,
  max disallow depth) and extracts sitemap URLs from robots-declared and
  `/sitemap.xml`. `http_methods.py` probes OPTIONS/HEAD/GET for allowed
  methods (TRACE → MEDIUM), page title, and content type; a new
  `HttpClient.request(method, …)`/`BaseModule.http_fetch` supports the
  non-GET probes with the same non-raising retry semantics. URL quick depth
  now selects headers + http_methods and the deep profile selects all five
  website collectors (plus domain/certificate); CLI/engine register them.
  Tests use an HTML fixture corpus (`tech.html`, `robots.txt`, `sitemap.xml`,
  favicon bytes) covering detection, cookie parsing, missing-protection and
  TRACE severities, and IPv4/IPv6-styled deep scans persisted to SQLite.
- Phase 11 — email module: address classification via `modules/email/`.
  `validation.py` syntax-checks, splits local/domain, and flags disposable
  providers against a bundled blocklist (extendable via
  `email.disposable_extra`). `mx.py` probes mail infrastructure over the
  shared DoH endpoint: MX presence with host A-resolution, SPF
  (includes + all-qualifier) and DMARC (policy/pct) parsing. `gravatar.py`
  probes the public avatar endpoint with `d=404` for existence. The two
  registered collectors are `EmailModule` ("email", validation + MX/SPF/DMARC
  + Gravatar with per-stage degradation to low-severity findings) and
  `BreachModule` ("breach", HIBP v3, `requires_keys=("hibp",)`). A missing
  API key emits a planner-level "skipped" run instead of an error, per the
  done criteria; unauthorized keys surface a MEDIUM finding. New
  `HttpClient.request`/`fetch`/`BaseModule.http_fetch` accept extra `headers`
  (for the HIBP API key). EMAIL deep profile selects
  email + breach + domain; quick selects the email collector. Tests cover
  syntax/blocklist units, mocked DoH+avatar+HIBP probes (200/404/401/503/
  transport), and quick/deep engine scans persisted to SQLite.
- Phase 0 — brand identity (`assets/logo.svg`, `assets/icon.svg`),
  `docs/brand/BRAND.md`, coding standards, git workflow, threat model, and
  privacy statement; folder architecture skeleton.
- Phase 1 — repository foundation: README, GPL-3.0 license, contributing and
  conduct documents, security policy, roadmap index, uv environment,
  Black/Ruff/Mypy/Pytest configuration, CI workflow, pre-commit hook, and
  smoke tests.
- Phase 2 — core architecture: constants and exception hierarchy, layered
  configuration, logging with secret redaction and scan-context binding,
  async TTL cache, async SQLite connection layer, fail-soft plugin loader,
  priority task scheduler, asyncio worker pool, scan engine facade, and
  unit tests for every component.
- Phase 3 — database layer: full schema (`targets`, `scans`, `findings`,
  `reports`, `plugins`, `api_keys`, `logs`, `history`, `settings`) with
  documented design in `docs/Database_Schema.md`, forward-only migration
  runner, typed repository layer with frozen record dataclasses, engine
  result-sink persistence, plugin metadata sync, and round-trip tests on
  temp databases. Engine scan timestamps now use wall clock for
  persistence.
- Phase 4 — CLI: Typer-based interface with `scan`, `report`, `history`,
  `config`, `plugin`, `doctor`, and `update` commands; `python -m cli` and
  `scripts/intelxtract` entry points; engine/worker-pool completion hooks
  (`on_module_done`, `on_task_done`); `ScanRepository.list`/`list_detailed`;
  SQLite connections now run in autocommit so writes survive process exit;
  CLI test suite via `typer.testing.CliRunner`.
- Phase 5 — GUI: PySide6 desktop shell with sidebar navigation and dark QSS
  theme from BRAND tokens; pages for Dashboard, Quick/Deep Scan (module
  checklist), Results, Reports, History, Plugins, API Manager, Settings, and
  About; `EngineBridge` running the asyncio engine on a worker `QThread` with
  queued Qt signals into the main thread; read-only SQLite sync helpers;
  `intelxtract-gui` entry point; offscreen smoke test suite
  (`QT_QPA_PLATFORM=offscreen`).
- Phase 6 — input engine: `core/input_engine.py` with a precedence-documented
  classifier (URL, email, IP v4/v6 with ports, hash md5/sha1/sha256, file
  path/dotfile/extension, domain with IDN→punycode, username, unknown);
  `parse_target`/`normalize` producing canonical `NormalizedTarget`
  (punycoded host, hex-lowercased hash, default URL scheme, compact IPv6)
  with actionable `ValidationError`s; `select_modules` selection map
  (quick/deep/custom profiles) now consumed by the scan planner with a
  fallback to all registered modules; the engine's default classifier now
  uses the real input engine instead of returning `unknown`; 87 table-driven
  classification/normalization/selection tests.
- Phase 7 — module system: `core/models.py` with the `Finding` dataclass
  (`module`, `title`, `severity`, `confidence`, `data`, `evidence`,
  `collected_at`) normalized from raw module output, deduplicated by a stable
  SHA-256 content hash, and carried on `ModuleResult`; `modules/base.py`
  `BaseModule` ABC (metadata, `validate`, `run`, `parse`, `export`, timeout/
  retry hooks) and `modules/registry.py` `ModuleRegistry` for discovery of
  packages under `modules/`, name-collision handling, and per-name enable/
  disable; `core/http_client.py` lazily-constructed aiohttp `HttpClient` with
  retry; the engine's `ModuleContext` now carries the shared HTTP session and
  an `api_key()` accessor, plans skip modules with unconfigured
  `requires_keys`, extracts and dedupes `ModuleResult` findings, and closes
  the HTTP client per scan; DB migration 2 adds `findings.title`, `evidence`,
  `content_hash`, and `collected_at` persisted through `FindingRepository`;
  reusable test harness under `tests/modules/` (`DummyModule`,
  `KeyedDummyModule`, `FakeHttpClient`, `make_module_context`) with the dummy
  module executing end-to-end through the engine into SQLite.
- `.env` support in `core/config.py` (`load_env_file`): API keys and other
  secrets can live in a git-ignored `.env` file (template in
  `.env.example`); existing environment variables are never overridden.
- Phase 8 — domain module: five collectors under `modules/domain/` —
  `whois.py` (RDAP registrar/dates/nameservers/contacts with email-redaction
  option and DNSSEC status), `dns.py` (DoH A/AAAA/CNAME/NS/MX/TXT plus SPF,
  DMARC, and a bounded DKIM selector probe), `ssl.py` (stdlib asyncio TLS
  handshake exposing subject, issuer, validity, SANs, and self-signed/
  expired flags), `subdomain.py` (passive certificate-transparency listing
  via crt.sh), and `http.py` (https/http probes, redirect chains,
  robots.txt/sitemap.xml reachability, and pass-fail security-header checks
  for HSTS/CSP/XFO/referrer/permissions). `HttpClient.fetch()` returns a
  non-raising `HttpResponse` (status/headers/body/redirects) for the probes;
  the quick/deep selection maps now list the domain modules; the CLI scan
  registers the discovered domain collectors. All network access is mocked
  in tests via `tests/modules/fixtures/` recorded payloads (RDAP/DoH/crt.sh/
  HTTP), covering each module plus an end-to-end engine run persisted into
  SQLite.

### Fixed

- Removed the hard-coded placeholder API key from the Phase 7 test harness
  (`tests/modules/fakes.py`); secrets are no longer committed and instead
  flow from the environment or the `.env` file.

[Unreleased]: https://keepachangelog.com/en/1.1.0/
