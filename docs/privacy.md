# Privacy Statement

IntelXtract is a **local-first** OSINT tool. This statement explains what
data the application stores, what leaves your machine, and what never
leaves it.

## Principles

1. **Local-first** — scan data, findings, reports, settings, and history
   live on your machine in files you control.
2. **No telemetry** — the application never phones home: no analytics, crash
   reporting, usage tracking, or update pings that identify you.
3. **No account** — no registration, no login, no cloud sync (until/unless a
   future self-hosted collaboration feature is explicitly deployed by you).
4. **Opt-in egress** — network traffic happens only to (a) targets you
   ask to scan, (b) data providers required by enabled modules, and
   (c) services you explicitly configure (API keys, proxy, AI endpoint).

## Data stored on your device

| Data | Location | Purpose |
|------|----------|---------|
| Targets & scan history | Local SQLite DB | History, diffing, scheduling |
| Findings & correlation graph | Local SQLite DB | Results, reports, risk scores |
| Reports | `exports/` (configurable) | Your exports; delete anytime |
| Settings | `config/settings.json` | Preferences (no secrets) |
| Encrypted API keys | DB `api_keys` table / OS keychain | Calling providers you chose |
| Logs | `logs/` | Diagnostics; secrets redacted |
| Cache | `cache/` | Performance only |

**Data you scan may include personal data about third parties** (e.g.,
public WHOIS contacts, profile pages). You are responsible for handling
that data lawfully — see `docs/threat_model.md` (ethical boundary) and the
acceptable-use terms in `README.md`.

## What leaves your machine

| Egress | When | Data sent |
|--------|------|-----------|
| Scan targets you enter | Every scan | Normal protocol traffic only (DNS queries, WHOIS, HTTP GET/HEAD, TLS handshakes). No identifying banner beyond standard protocol metadata. |
| Public data APIs (CT logs, IP geolocation, RSS, site checks) | Enabled modules | The domain/IP/username being researched — nothing about you. |
| Key-gated providers (e.g., VirusTotal, HIBP, AbuseIPDB) | Only when you add a key and enable the module | The queried indicator + your provider API key (to that provider, over HTTPS). |
| AI endpoint (Phase 23) | Only if you explicitly enable it | The report payload you chose to send, to the endpoint **you** configured. Disabled by default. |
| PyPI (informational) | `intelxtract update` command only | Version metadata for comparison. |

Proxy: all egress can be routed through a user-configured proxy.

## What never leaves your machine

- Keys, passwords, or vault contents (except to the provider the key
  belongs to, as that provider's API requires).
- The local database, logs, config, or reports as a whole.
- Any background telemetry of any kind.
- Information about scans you have not run.

## Key handling

- API keys are stored encrypted (Fernet; OS keychain via `keyring` when
  available) with file permissions `0600`.
- Keys are redacted from logs, reports, and error messages.
- Deleting a key from the API Manager removes the ciphertext permanently.

## Retention & deletion

- There is no server-side copy to delete — everything is local.
- Full removal: delete the data directory (shown by
  `intelxtract config path`), the `config/` folder, and `logs/`/`cache/`.
- Individual cleanup: history and exports can be deleted from the UI/CLI
  (Phase 22+ where case-scoped deletion lands).

## Third parties

- Default operation contacts **no** third party other than scan targets and
  the public endpoints of enabled modules.
- Each key-gated provider processes the indicators you submit under its own
  privacy policy; review it before adding a key.
- The optional AI assistant sends data only to a user-supplied endpoint and
  discloses this in the UI at enable time.

## Children / sensitive use

IntelXtract is intended for professional, research, and educational use by
adults. Users are responsible for lawful collection and handling of personal
data (GDPR/CCPA and local equivalents apply to *your* processing).

## Changes

This statement is versioned with the repository. Material changes are noted
in `CHANGELOG.md` and must be reviewed at the phase gate that introduces a
new network egress or storage surface.
