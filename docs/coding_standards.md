# Coding Standards

Applies to all Python, QSS, SQL, JavaScript, and templates in IntelXtract.

## Enforcement

The gate below must pass before any phase is marked done:

```bash
ruff check . && black --check . && mypy . && pytest
```

- **Black** — formatting is non-negotiable; never hand-format around it.
- **Ruff** — linting (`E`, `F`, `I`, `B`, `UP`, `ASYNC`, `S`, `RUF` rules);
  security rules (`S`) are enabled deliberately, fix findings rather than
  adding `noqa` (a `noqa` requires an inline justification comment).
- **Mypy** — all new code is typed; no `# type: ignore` without a reason.
- **Pytest** — every module, command, and repository layer ships tests.

## Python style

- Target: Python 3.13+; use modern syntax (`X | None`, `match`, `type`
  aliases).
- Line length 88 (Black default); ruff matches it.
- Two-space indent is forbidden; Black governs all indentation.

## Naming

| Kind | Convention | Example |
|------|-----------|---------|
| Modules/packages | `snake_case` | `whois.py`, `worker_pool.py` |
| Classes | `PascalCase` | `ScanEngine`, `Finding` |
| Functions/methods | `snake_case` | `run_scan()` |
| Constants | `SCREAMING_SNAKE` | `DEFAULT_TIMEOUT` |
| Private | leading `_` | `_normalize_domain()` |
| Booleans | `is_` / `has_` / `can_` | `is_valid`, `has_key` |
| Async functions | same; callers must not block them | `async def fetch()` |

## Typing

- Every public function has full parameter and return annotations.
- Prefer `dataclass(frozen=True, slots=True)` or `TypedDict` for payloads;
  no bare `dict[str, Any]` across module boundaries.
- Use `Protocol` for interfaces (modules, plugins, repositories).
- mypy strictness increases per phase; do not weaken global config to land
  a feature.

## Async rules

- Library/network code is `async`; CPU-bound or blocking work
  (WHOIS, DNS resolver, file parsing) runs in `asyncio.to_thread` with a
  bounded pool.
- Never call `time.sleep()`, `requests`, or blocking I/O inside a coroutine.
- All network calls carry explicit timeouts; no bare `await session.get(...)`.
- Cancellation must be honored: catch `asyncio.CancelledError` only to clean
  up, then re-raise.
- Shared state across tasks is guarded or immutable; no unprotected globals.

## Error handling

- Raise from the custom hierarchy in `core/exceptions.py`; never raise bare
  `Exception` or `ValueError` from library code paths.
- `except Exception` is allowed only at task/pool boundaries where one failed
  module must not kill the scan — log it, mark the module `failed`, continue.
- No `except: pass`. Every swallowed error is logged with context.
- User-facing errors (CLI/GUI) explain cause + next step.

## Logging

- Use `core/logger.py`; no `print()` outside CLI presentation code.
- Log with structured context (`scan_id`, `module`, `target`), never with
  f-strings of secrets — API keys are redacted automatically by the logger.
- Levels: `DEBUG` diagnostics, `INFO` lifecycle, `WARNING` degradation,
  `ERROR` failures, `CRITICAL` only for abort-level faults.

## Security

- Secrets live only in the key vault (Phase 24); never in code, config
  files, logs, reports, or exceptions.
- Treat all module input (HTTP bodies, files, WHOIS text, EXIF, XML) as
  hostile: size limits, decompression-bomb guards, no `eval`/`pickle` on
  untrusted data, XML parsers resolve no entities.
- File parsers (PDF/image/Office) cap input size and run off the event loop.
- Follow the ethical boundary in `docs/threat_model.md`: public data and
  authorized APIs only; no exploitation, auth bypass, or brute force code.
- Dependencies: prefer stdlib; new runtime deps need justification in the
  phase report.

## Tests

- Layout mirrors source: `modules/domain/whois.py` →
  `tests/modules/domain/test_whois.py`.
- Names: `test_<behavior>_<condition>`; arrange-act-assert with no logic in
  tests.
- Unit tests never touch the network — mock HTTP/DNS or use recorded
  fixtures in `tests/fixtures/`. Network-dependent tests are marked
  `@pytest.mark.integration` and excluded from the default run.
- Every bug fix adds a regression test.

## Docstrings & comments

- Google-style docstrings on all public modules, classes, and functions
  (one-line summary; args/returns sections when non-obvious).
- Comments explain *why*, not *what*; delete comments that narrate code.
- No ASCII-art banners or decorative comments in source.

## File layout

- One module = one responsibility; keep files under ~500 lines (split when
  ruff complexity warnings appear).
- Imports: stdlib → third-party → first-party (`core`, `modules`, …), each
  group separated by a blank line (ruff `I` enforces order).
- No circular imports: dependency direction is
  `cli/gui → core → modules → database`; `modules` never import `cli`/`gui`.

## QSS / frontend

- All colors, fonts, radii, and spacing come from BRAND.md tokens — no
  magic hex values in QSS outside the theme file.
- Widget classes are namespaced (`ix-*`) to avoid Qt style collisions.

## SQL

- Schema changes go through migrations only (`database/migrations.py`);
  never alter a shipped schema in place.
- All queries use parameters — string interpolation of values is forbidden.
- Repositories are the only layer that executes SQL.
