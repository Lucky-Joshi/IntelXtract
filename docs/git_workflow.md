# Development Workflow

## Phase-gate process

Development proceeds one phase at a time per `docs/Phase_Plan.md`:

1. Implement the phase's sub-phases in listed order.
2. Run the verification gate:

   ```bash
   ruff check . && black --check . && mypy . && pytest
   ```

3. Flip the phase checkboxes to `[x]` in `docs/Phase_Plan.md`.
4. Deliver the completion report (sub-phases done, files added, gate results,
   deviations).
5. **Stop.** The next phase begins only after an explicit "continue".

Scope changes are added to `Phase_Plan.md` **between** phases, never mid-phase.

## Branching

| Branch | Purpose |
|--------|---------|
| `main` | Stable history; only phase-boundary commits land here directly |
| `feat/<phase>-<slug>` | Phase work, e.g. `feat/phase-2-worker-pool` |
| `fix/<slug>` | Bug fixes, e.g. `fix/whois-timeout` |
| `docs/<slug>` | Documentation-only changes |
| `chore/<slug>` | Tooling, dependencies, CI |
| `release/x.y.z` | Release stabilization (created at Phase 29) |

- Branch from `main`; keep branches short-lived (one phase or one fix).
- Merge with `--no-ff` so phase boundaries remain visible in history.
- Tags: `vMAJOR.MINOR.PATCH`, created at releases; tagging is fine locally,
  pushing tags is user-owned.

## Commits

Conventional Commits:

```
<type>(<scope>): <imperative summary>

<body: why, notable decisions>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`,
`build`.

- Subject ≤ 72 characters, imperative mood ("add", not "added").
- Scope = subsystem: `core`, `cli`, `gui`, `modules/domain`, `db`, `reports`,
  `plugins`, `ci`, `docs`.
- One logical change per commit; never commit formatting noise mixed with
  behavior changes.
- Pre-commit hook runs `ruff check` + `black --check` (installed in Phase 1).

### Phase-boundary commits

Each completed phase ends with one or more commits summarizing it:

```
feat(phase-4): add Typer CLI with scan/report/history commands
```

## Push policy

- **Local commits are expected; pushing is user-owned.** No `git push`,
  no remote configuration, no force-push, no history rewrites unless the
  user explicitly instructs it.
- Do not amend commits that were reported in a phase report.

## Code review (solo-friendly)

- Self-review each diff against `docs/coding_standards.md` before the gate.
- Phase reports list files touched so the user can diff quickly:
  `git show --stat <phase-commit>`.

## Dependencies

- Runtime deps → `requirements.txt`; dev deps → `requirements-dev.txt`;
  installed with `uv pip install -r …`.
- Adding a dependency is a noted decision in the phase report (license,
  maintenance status, why stdlib is insufficient).
- Keep versions pinned with `==` in both files; upgrades are deliberate
  commits.

## Issue / task tracking

- Work items derive from `Phase_Plan.md`; no separate tracker required.
- Bugs found between phases are logged in the plan's backlog section or as
  a `fix/` branch, prioritized before the next phase starts if they block it.
