# IntelXtract — reconnaissance report

**Target:** example.com
**Generated:** 2026-10-11T14:20:19
**Overall risk:** LOW

## Executive summary

- LOW overall risk (0/100) assessed for example.com across 37 finding(s).
- MEDIUM — HTTP: missing content-security-policy in http.
- MEDIUM — HTTP: missing strict-transport-security in http.
- LOW — HTTP: missing permissions-policy in http.

## Risk overview

- **TLS:** 0.0 across 0 rule(s)
- **HEADERS:** 0.0 across 0 rule(s)
- **DNS:** 0.0 across 0 rule(s)
- **EXPOSURE:** 0.0 across 0 rule(s)

## Findings

| severity | module | title | evidence |
| --- | --- | --- | --- |
| medium | http | HTTP: missing content-security-policy | content-security-policy not sent over https |
| medium | http | HTTP: missing strict-transport-security | strict-transport-security not sent over https |
| low | http | HTTP: missing permissions-policy | permissions-policy not sent over https |
| low | http | HTTP: missing referrer-policy | referrer-policy not sent over https |
| low | http | HTTP: missing x-frame-options | x-frame-options not sent over https |
| low | http | HTTP: no robots.txt | HTTP 404 |
| low | http | HTTP: no sitemap.xml | HTTP 404 |
| info | dns | DNS: A records | 2 record(s) |
| info | dns | DNS: AAAA records | 2 record(s) |
| info | dns | DNS: DKIM selector '2020' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector '2021' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'default' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'dkim' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'google' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'mail' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'pacman' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 's1' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 's2' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 's3' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'selector1' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'selector2' | "v=DKIM1; p=" |
| info | dns | DNS: DKIM selector 'selector3' | "v=DKIM1; p=" |
| info | dns | DNS: DMARC record | "v=DMARC1;p=reject;sp=reject;adkim=s;aspf=s" |
| info | dns | DNS: MX records | 1 record(s) |
| info | dns | DNS: NS records | 2 record(s) |
| info | dns | DNS: SPF record | "v=spf1 -all""_k2n1y4vw3qtb4skdx9e7dxt97qrmmq9" |
| info | dns | DNS: TXT records | 2 record(s) |
| info | http | HTTP: http responds | HTTP 200 at http://example.com/ |
| info | http | HTTP: https responds | HTTP 200 at https://example.com/ |
| info | news | News: timeline | 12 recent article(s) across 1 feed(s) |
| info | ssl | SSL: certificate | [] from ['unknown'] |
| info | ssl | SSL: subject alternative names | 0 SAN(s) |
| info | whois | RDAP: DNSSEC signed | delegation_signature=signed |
| info | whois | RDAP: nameservers | ELLIOTT.NS.CLOUDFLARE.COM, HERA.NS.CLOUDFLARE.COM |
| info | whois | RDAP: registrar | None |
| info | whois | RDAP: registration dates | expires 2027-08-13T04:00:00Z |
| info | whois | RDAP: status flags | client delete prohibited; client transfer prohibited; client update prohibited |

## Timeline

- 1773126000 — Wget Command: How to Use It + 12 Practical Examples - Hostinger
- 1774594800 — How to set up Nginx Proxy Manager with Docker Compose - TheServerSide.com
- 1774940400 — Streamline your Amazon EKS deployments with Gateway API support for AWS Load Balancer Controller and Amazon VPC Lattice - Amazon Web Services (AWS)
- 1776150000 — Scaling MCP adoption: Our reference architecture for simpler, safer and cheaper enterprise deployments of MCP - Cloudflare Blog
- 1778396400 — How to configure an Nginx reverse proxy server - TheServerSide.com
- 1784215543 — How to log in to WordPress dashboard: 3 simple methods - Hostinger
- 1785394800 — Adform compromised to serve crypto stealer via supply chain attack - DoublePulsar
- 1786172400 — I built my own Wayback Machine, and now I never lose web pages - MakeUseOf
- 1786431600 — 3 AI Prompts for Google Ads - Practical Ecommerce
- 1790233200 — Placeholder third-party[.]com Referenced Across 1,700+ Repositories Now Serves Malicious Content - The Hacker News
- 1791264192 — Example.com redesign adds rotating languages, splits page to cut bot traffic - news.lavx.hu
- 1791364200 — example.com, famous for being 'almost completely empty,' has undergone a major redesign, now supporting six languages, and comes with a warning: 'Do not use it for testing or monitoring.' - GIGAZINE
- 1791708278 — scan started
- 1791708308 — scan finished

## Methodology

- Passive reconnaissance only: DNS, RDAP/WHOIS, certificate transparency, and HTTP fingerprints gathered from public sources.
- Indicators originate from the configured module set and are de-duplicated by content hash before scoring.
- Risk scores are deterministic weights over concrete findings; every contributing rule is listed in the risk overview.
