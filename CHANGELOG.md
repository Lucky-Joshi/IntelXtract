
### Phase 19 — Reporting

- `reports/brand.py` — brand tokens parsed from `BRAND.md` (accent, page/card background, text, muted, border) with defaults; `BRAND.md` added at repo root as the visual source of truth (S19.2).
- `reports/builder.py` — shared `ReportModel`: executive summary, severity counts, module counts, timeline, evidence refs (top-EVIDENCE_LIMIT, critical-first), methodology; deterministically re-derives correlation (`TargetType`-coerced) and risk from findings so persisted pre-P16/P17 scans still get full reports; fixed `generated_at` support for stable snapshots.
- `reports/exporter.py` — `export_report()` for `json|html|csv|md|pdf`: JSON = canonical model, CSV = one row per finding (critical-first), Markdown = one-file report, HTML = Jinja2 template rendered from brand tokens, PDF = WeasyPrint when its system libraries exist, otherwise a print-friendly HTML fallback with an explicit warning (never fails).
- `templates/report.html.j2` — single template with an on-screen styled mode and a print-mode CSS switching to plain black-on-white; sections: brand header, executive summary, risk overview with per-category bars + rule trace, severity-grouped findings table, module counts, timeline, methodology/evidence, timestamped footer.
- `cli/report` — replaced the JSON stub: every format (`--format`) writes bytes to `exports/report-<id>.<ext>` or `--out`, prints format/fallback warnings, and registers the report in the `reports` table (S19.5).
- `gui/pages/reports.py` — points users at the CLI formats instead of implying later GUI-only generation.
- Tests: golden JSON snapshot (`tests/reports/golden/report.json`), model section/ordering tests, determinism, CSV row counts incl. empty case, Markdown sections, HTML brand/section markers, PDF fallback (WeasyPrint absent) + fake-weasyprint byte path, unsupported-format raise, CLI JSON round-trip + parametrized format loop + PDF-fallback file/warning checks.

### Phase 16 — Correlation Engine

- `core/entities.py` — stable entity model (10 kinds, normalized value hash IDs) + per-module extractors over `Finding.data`.
- `core/correlation.py` — NetworkX MultiDiGraph linker: `resolves_to`, `registered_by`, `issued_to`, `same_email`, `part_of`, `mentions`, `profile`, `uses` edges with confidence.
- `ScanResult.correlation` — deterministic graph JSON (entities/edges/stats) computed at scan end; included in `to_dict`/exports, never fails a scan.
- `requirements.txt`: pin `networkx==3.7`.
- 9 new tests (entity normalization/ids, extractor aggregation, expected edge set, connected components, cross-scan determinism, empty-findings).


### Phase 17 — Risk Engine

- `core/risk_rules.py` — documented rule table (module + title pattern → category + weight): expired/self-signed TLS, no HTTPS, TRACE, missing HSTS/CSP/XFO/XCTO/Referrer/Permissions, server disclosure, insecure cookies, missing/weak SPF + DMARC + MX, absent DNSSEC, breach exposure, GPS metadata, disposable email.
- `core/risk.py` — pure `assess_risk()` scoring: category sub-scores (TLS/HEADERS/DNS/EXPOSURE) with documented ceilings, 0-100 score → `low|medium|high|critical`, deterministic de-duped/ordered rule trace, plain-language top-risk summary.
- `ScanResult.risk` — computed at scan end from flattened findings, included in `to_dict()`/exports, guarded so it never fails a scan.
- 10 new tests: rating bands, golden scores, category ceilings, 100-cap saturation, cookie flag weights, weak SPF/DMARC predicates, input-order determinism, engine scan smoke + cross-scan stability.


### Phase 18 — Visualization

- `gui/viz/base.py` — `VizWidget` canvas: one `draw()` feeds the screen and in-memory PNG (`QImage`) / SVG (`QSvgGenerator`) exports; `export_png`/`export_svg` write report files (S18.5).
- `gui/viz/graph_widget.py` — entity relationship graph built from the Phase 16 correlation payload; dependency-free deterministic Fruchterman-Reingold layout (no numpy needed), edges colored by type, target ring highlight (S18.1).
- `gui/viz/timeline.py` — scan + news timeline on a shared time axis with `timeline_events()` normalizing payloads (S18.2).
- `gui/viz/charts.py` — paint-based risk-category pie, module/severity bar charts, and scan trend line with `severity_bars`/`module_bars`/`trend_points` helpers (S18.3).
- `gui/viz/world_map.py` — offline tile-less coarse world map (committed 135-country polygon set) dotting `Geo: IP location` findings by country or explicit lat/lon (S18.4).
- `gui/pages/results.py` — new Visualization tab (Graph/Timeline/Charts/Map); `normalize_result` now passes `correlation`/`risk` through.
- 8 new tests: offscreen widget PNG/SVG rendering, deterministic graph export, timeline sorting/dedup, bar helpers, map grouping, PNG file writes, results-page wiring.

# Changelog

All notable changes to IntelXtract are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


### Phase 15 — News Module

- `modules/news/` — Google News RSS + configured RSS/Atom feeds (`rss.py`, `feeds.py`, `timeline.py`, `collector.py`).
- Deterministic timeline builder: dedupe by URL/guid, newest-first, undated last, capped by `news.max_items`.
- Config: `news.{google,max_items,feeds,feeds_by_domain,feeds_extra}`; registered `modules.news` on DOMAIN deep scans.
- Offline-safe: every feed failure degrades to an `unavailable` LOW finding rather than crashing.
- 21 new tests (feed fixtures, date parsing, dedupe, feeds config, engine + persistence).

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
- Phase 12 — username module: presence checks across 36 bundled public
  profile sites (`modules/username/sites.json` with per-site status/marker
  rules; operator sites via `username.sites_extra` or a full
  `username.sites_path` override). `social.py` probes sites concurrently with
  a global semaphore plus per-site request pacing, resolving each verdict
  conservatively: only conclusive status codes or body markers yield
  exists/missing, anything else (redirects, bot walls, 5xx) is `unknown`.
  `enrichment.py` parse-lightly pulls the public GitHub profile (avatar,
  display name, bio, stats) when the account exists; blocks/rate limits
  quietly skip it. The registered `username` collector emits an INFO finding
  per confirmed profile plus a `Username: profile summary` aggregate, and
  marks the run `degraded` (LOW finding) when every verdict is unknown.
  Tests cover registry validation, exists/missing/blocked/odd-status verdicts,
  marker precedence (Instagram-style 200 + missing-marker), enrichment
  failure modes, and mocked quick scans persisted to SQLite.
- Phase 13 — certificate module: deep TLS/certificate intelligence in three
  parts. `details.py` parses captured PEM/DER certificates (cryptography)
  into subject/issuer DNs, SANs, signature algorithm, serial, validity,
  key/extended-key usage, CA flag, CT poison mark and SCT list, with
  pure-data risk classification (weak SHA-1/MD5 signatures, expired or
  expiring-soon certs, self-signed, precertificates). `tls_probe.py`
  handshakes TLS 1.0–1.3 per version and reports the negotiated cipher,
  flagging deprecated protocols and RC4/3DES/CBC/NULL/EXPORT ciphers.
  `transparency.py` aggregates crt.sh history — issuers, validity windows,
  SAN sets, first/last seen, wildcard-normalized related names. The
  registered `certificate` collector combines all three, degrading to
  `partial`/`unknown` when the live handshake or crt.sh is unavailable.
  Live hooks are module-level and monkeypatched in tests, so no unit test
  opens a TLS connection; certificate fixtures are built offline.
- Phase 14 — metadata module: document/file property extraction for
  user-provided files. `pdf.py` reads PDF document dictionaries via pypdf
  (title, author, producer, creator, page count, PDF version, creation/mod
  timestamps normalized to ISO-8601). `image.py` reads only EXIF header
  blocks with Pillow — make/model, software, timestamps, artist, lens — and
  converts GPS DMS rationals to signed decimal degrees, guarded by a
  decompression-bomb pixel cap and never decoding pixel payloads. `office.py`
  parses OOXML ``.docx``/``.xlsx``/``.pptx`` core/app property parts
  directly from the zip container (creator, lastModifiedBy, company, dates,
  application), with legacy binary ``.doc`` explicitly out of scope. The
  registered `metadata` collector dispatches on extension and collapses
  malformed or unsupported files to informational findings instead of
  failing the scan. Fixture files (sample PDF/JPEG/docx + malformed
  variants) are committed under `tests/modules/fixtures/metadata/`.
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
