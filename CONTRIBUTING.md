# Contributing to IntelXtract

Thanks for your interest. IntelXtract is developed strictly phase-by-phase;
read this page and [`docs/git_workflow.md`](docs/git_workflow.md) before
sending changes.

## Ground rules

- Work follows [`docs/Phase_Plan.md`](docs/Phase_Plan.md): one phase at a
  time, reported and gated before the next begins.
- All code must satisfy the verification gate:

  ```bash
  ruff check . && black --check . && mypy . && pytest
  ```

- Follow [`docs/coding_standards.md`](docs/coding_standards.md) — no
  exceptions without an inline, justified `noqa`/`type: ignore`.
- Stay inside the ethical boundary: public data and authorized APIs only
  ([`docs/threat_model.md`](docs/threat_model.md)).
- **No secrets** in code, commits, config, logs, or tests.

## Development setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repository-url> IntelXtract
cd IntelXtract
uv venv .venv
uv pip install -r requirements.txt -r requirements-dev.txt

# activate in your shell
source .venv/bin/activate

# run the suite
pytest
```

The pre-commit hook (`scripts/hooks/pre-commit`, installed at `git init`)
runs `ruff check` and `black --check` automatically.

## Making changes

1. Branch from `main` using the naming in `docs/git_workflow.md`
   (`feat/<phase>-<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`).
2. Implement — keep commits small and logical, Conventional Commit style.
3. Add/update tests for every behavior change; unit tests never hit the
   network (use fixtures under `tests/fixtures/`).
4. Run the full gate before handing anything off.
5. Update `docs/Phase_Plan.md` only at phase boundaries (status flips are
   part of the phase report).

## Reporting bugs

Open an issue with:

- IntelXtract version (`intelxtract --version` once the CLI ships) and OS
- Exact command/action and observed vs. expected behavior
- Relevant log excerpt (`logs/`, with secrets already redacted)

Security issues: follow [`SECURITY.md`](SECURITY.md) — **do not** open a
public issue.

## Suggesting modules or plugins

- Core modules: open an issue describing the data source, whether it needs
  an API key, its terms of service, and target types it applies to.
- External integrations should usually be plugins — see the plugin SDK
  docs (Phase 20).

## Pull requests / pushes

- Prefer PRs once a remote exists; the maintainer owns merging and pushing.
- Contributors push only their own feature branches when explicitly
  permitted by the maintainer. `main` is never force-pushed.

## License

By contributing you agree your contributions are licensed under
GPL-3.0-or-later, same as the project.
