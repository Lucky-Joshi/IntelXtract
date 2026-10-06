# Architecture

This document describes the high-level system structure used by the IntelXtract platform. The architecture is intentionally layered: user interfaces feed into a central scan engine, which coordinates workers, correlates results, scores risk, and persists output in a storage layer.

## System overview

```text
                     +----------------------+
                     |      User (CLI)      |
                     +----------+-----------+
                                |
                     +----------v-----------+
                     |      User (GUI)      |
                     |      (PySide6)       |
                     +----------+-----------+
                                |
                   +------------v-------------+
                   |     Core Scan Engine      |
                   +------------+-------------+
                                |
        +-----------------------+-----------------------+
        |                       |                       |
+-------v------+      +---------v---------+    +--------v--------+
| Input Parser |      | Task Scheduler    |    | Scan Manager    |
+--------------+      +-------------------+    +-----------------+
                                |
                                |
                 +--------------v--------------+
                 | Async Worker Pool           |
                 | asyncio + aiohttp           |
                 +--------------+--------------+
                                |
      --------------------------------------------------------------
      |        |         |        |         |        |              |
+-----v--+ +---v---+ +---v---+ +--v---+ +---v---+ +--v---+ +--------v------+
| WHOIS  | | DNS   | | SSL   | | IP   | | Email | | News | | Username Scan |
+--------+ +-------+ +-------+ +------+ +-------+ +------+ +---------------+
      |        |         |        |         |        |              |
      ---------------------------------------------------------------
                                |
                   +------------v------------+
                   | Data Correlation Engine |
                   +------------+------------+
                                |
                 +--------------v--------------+
                 | Risk Scoring Engine         |
                 +--------------+--------------+
                                |
                 +--------------v--------------+
                 | SQLite / PostgreSQL         |
                 +--------------+--------------+
                                |
             +------------------+-------------------+
             |                  |                   |
     +-------v------+   +-------v------+   +--------v--------+
     | HTML Report  |   | PDF Report   |   | JSON / CSV      |
     +--------------+   +--------------+   +-----------------+
```

## Key layers

- User interfaces: CLI and GUI entry points
- Core scan engine: orchestration, scheduling, and work execution
- Worker pool: asynchronous collection of domain, IP, email, and metadata checks
- Intelligence layer: correlation and risk scoring across findings
- Persistence and output: database storage plus report generation in multiple formats