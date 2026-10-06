# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| pre-release (`main`) | yes (best effort) |
| < 1.0 | yes (best effort) |
| older | no |

IntelXtract is pre-1.0; fixes land on `main`. Once releases start, the two
most recent minor versions are supported.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Report privately using one of these channels:

1. GitHub **Security Advisory → Report a vulnerability** on this repository
   (preferred once the remote exists).
2. Email the maintainer (published on the GitHub profile of the repository
   owner) with subject line `[SECURITY] IntelXtract`.

Include:

- Affected version / commit and environment (OS, Python version)
- Description of the issue and its impact
- Reproduction steps or a proof of concept (non-destructive)
- Any known workarounds

### What to expect

- Acknowledgement within **7 days**
- Assessment and status update within **14 days**
- Fix or mitigation plan agreed before any public disclosure
- Credit in `CHANGELOG.md` unless you prefer to remain anonymous

## Safe harbor

Security research conducted in good faith and in accordance with this policy
is welcomed. We will not pursue legal action against researchers who:

- Avoid privacy violations, data destruction, and service disruption
- Only exercise accounts/data they own or have explicit permission to test
- Report findings promptly and keep them confidential until a fix ships

## Scope

**In scope:** IntelXtract itself — vulnerabilities in its code that allow,
for example: secret disclosure (API keys, vault contents), command/file
injection through scan inputs, report XSS, unsafe parsing of hostile scan
results, path traversal in exports, or unintended data exfiltration
(see `docs/threat_model.md`).

**Out of scope:**

- Findings about third-party services, scan targets, or data providers
  (report those to the affected provider)
- Denial-of-service against IntelXtract by overwhelming it with traffic
  (rate limits exist; resource-exhaustion bugs with realistic inputs are
  in scope)
- Issues in dependencies without a demonstrated path into IntelXtract
- Social engineering, phishing, or physical attacks
- Findings requiring an already-compromised host

## Hardening references

- Design-time threats and mitigations: [`docs/threat_model.md`](docs/threat_model.md)
- Privacy/data handling: [`docs/privacy.md`](docs/privacy.md)
- Secret handling standards: [`docs/coding_standards.md`](docs/coding_standards.md)
