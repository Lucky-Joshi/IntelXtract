# Roadmap

IntelXtract ships one phase at a time. The **authoritative, living** schedule
with sub-phases, done criteria, and status is
[`docs/Phase_Plan.md`](docs/Phase_Plan.md). The original vision and full
phase descriptions live in
[`docs/Development_Plan.md`](docs/Development_Plan.md).

## Milestones

| Milestone | Name | Phases | Outcome |
|-----------|------|--------|---------|
| A | Planning & Foundation | 0–1 | Brand, governance, tooling, repo foundation |
| B | Core Engine | 2–4 | Engine, config, logging, cache, database, CLI |
| C | Interface | 5 | PySide6 desktop application |
| D | Collection Modules | 6–15 | Domain, IP, website, email, username, certificate, metadata, news |
| E | Intelligence | 16–17 | Correlation graph + risk scoring |
| F | Presentation | 18–19 | Visualization + multi-format reports |
| G | Platform & Extensibility | 20–21 | Plugin SDK + scheduler/change detection |
| H | Collaboration & AI | 22–23 | Case management + optional AI assistant |
| I | Hardening & Release | 24–29 | Settings/vault, performance, testing, docs, packaging, v1.0 |

## Current status

Progress is tracked in the summary table of
[`docs/Phase_Plan.md`](docs/Phase_Plan.md). Completed phases flip their
checkboxes there and are recorded in [`CHANGELOG.md`](../CHANGELOG.md).

## Post-1.0 backlog

REST API, watchlists & alerting, threat-intel feed ingestion, full batch
scans, team workspaces, localization — see the
"Unscheduled / future" section of [`docs/Phase_Plan.md`](docs/Phase_Plan.md).
