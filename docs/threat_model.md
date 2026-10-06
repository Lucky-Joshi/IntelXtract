# Threat Model

Scope: the IntelXtract desktop/CLI application, its local data store, and the
network traffic it generates while performing OSINT collection.

## Goals

- Protect user secrets (API keys, config) at rest and in logs/reports.
- Protect the user from hostile data returned by scan targets.
- Keep collection within ethical, legal, and provider-ToS boundaries.
- Remain local-first: no telemetry, no third-party exfiltration by default.

## Assets

| Asset | Sensitivity | Location |
|-------|-------------|----------|
| API keys for third-party services | Critical | Key vault (encrypted at rest, Phase 24) |
| Scan history & findings | High | Local SQLite DB (`~/.local/share/intelxtract` or configured path) |
| Reports (may contain personal data) | High | `exports/` |
| Configuration (paths, limits, proxy) | Medium | `config/settings.json` |
| Logs | Medium | `logs/` — must never contain secrets |
| The host machine itself | Critical | User workstation |

## Trust boundaries

```text
[User] ── input ──> [IntelXtract app]
                        │
                        ├── read/write ──> [Local FS: DB, config, logs, exports]
                        │
                        └── network ──> [Scan targets: DNS, WHOIS, HTTP(S), CT logs]
                                    ──> [Optional APIs: VirusTotal, HIBP, …]  (key-gated)
                                    ──> [Optional AI endpoint]                (opt-in only)
```

Everything beyond the app boundary is **untrusted**, including responses
from targets the user deliberately scans.

## Adversaries & threats

| # | Threat | Vector | Mitigation |
|---|--------|--------|------------|
| T1 | Malicious scan target returns hostile payload (huge HTML, decompression bomb, malformed cert, evil EXIF/XML) | HTTP/file parsing modules | Response size caps, timeout budget, `defusedxml`/safe parsers, no `eval`/`pickle`, file parsers off the event loop with size limits (Coding Standards §Security) |
| T2 | XSS/script injection into reports | Findings containing HTML/JS rendered in HTML report | Jinja2 auto-escape everywhere; raw values escaped; CSP meta tag in report template (Phase 19) |
| T3 | Secret leakage | Keys appearing in logs, reports, exceptions, traces | Logger redaction filter; vault accessor is the only key source; reports exclude secrets by construction; grep-gate in tests |
| T4 | Local theft of DB/keys | Another user/process on the machine | File perms `0600`/`0700`; vault encryption (Fernet + keyring when available); documented residual risk: same-user malware can read keys (OS keychain is the upgrade path) |
| T5 | Supply-chain compromise | Malicious/compromised dependency | Minimal dependency set, pinned `==` versions, stdlib-first policy, plugin imports are opt-in and version-checked (Phase 20) |
| T6 | Runaway resource use | Unbounded concurrency, retry storms, scheduler loops | Worker-pool limits, per-host semaphores, bounded retries with backoff, scheduler overlap prevention (Phases 21, 25) |
| T7 | SSRF-style abuse via targets | User-supplied URL redirects to internal hosts (localhost, RFC1918, cloud metadata) | Default: block redirects to loopback/link-local/metadata ranges (`169.254.169.254`) with an explicit opt-in setting for authorized internal testing |
| T8 | Rate-limit / ToS violations | Aggressive scanning of third-party services | Global + per-host rate limits, robots.txt respect on profile checks, provider-specific throttles, API-key-gated modules skip politely without keys |
| T9 | Plugin escape | Third-party plugin doing anything it wants | Phase 20: manifest gating, isolated import failure handling, user must enable plugins explicitly; documented that plugins are **trusted code** — same privilege as the app (residual risk accepted and disclosed) |
| T10 | AI prompt exfiltration | Sending findings to an external model | AI disabled by default; opt-in per Phase 23 with explicit disclosure of which endpoint receives data; no keys/PII beyond the report payload |
| T11 | Audit gap | Undetected misuse of collected data | Scan history persisted locally (`history`), audit-relevant actions logged (settings/key changes) — visible to the user only |

## Ethical & legal boundary (design constraint)

- Only **publicly available** information and **authorized APIs**.
- No exploitation, exploitation PoCs, credential attacks, brute force,
  vulnerability exploitation, or unauthorized access code will be added to
  any module or plugin shipped in this repository.
- Open-port/service identification (vision §IP Intelligence) is only
  implemented if it stays within passive/authorized scope; otherwise it
  remains out of scope.
- Modules respect robots.txt where checking profiles and never bypass
  authentication, CAPTCHAs, or access controls.
- `SECURITY.md` tells reporters how to disclose issues in IntelXtract
  itself; it is not a channel for reporting findings about third parties.

## Out of scope

- Multi-user server deployment hardening (until the optional REST API /
  self-hosted phases).
- Protecting the user from an already-compromised host.
- Anonymizing the user's traffic (no Tor/proxy management beyond
  user-configured proxy support).
- Forensic anti-forensics; this is an investigation aid, not a covert tool.

## Review cadence

- Re-review this model at each phase boundary that adds network I/O,
  parsing of untrusted data, secret handling, or a new trust boundary
  (notably Phases 11, 20, 23, 24, 28).
- Record model changes in the phase report.
