# Pull Request Template

## Description

Briefly describe the changes in this PR.

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Refactoring (no functional changes)
- [ ] Test improvement
- [ ] Dependency update

## Related Issues

Closes #<issue_number>
Relates to #<issue_number>

## Checklist

- [ ] I have read the [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/git_workflow.md](docs/git_workflow.md)
- [ ] My code follows the project's coding standards (`ruff check . && black --check .`)
- [ ] I have added type hints to all new functions/classes
- [ ] I have run `mypy .` and it passes
- [ ] I have added/updated tests for my changes
- [ ] I have run `pytest` and all tests pass (756+ tests)
- [ ] I have updated relevant documentation (user guide, developer guide, plugin SDK, etc.)
- [ ] I have updated `CHANGELOG.md` with a brief entry under the appropriate phase
- [ ] My changes are scoped to a single phase (see `docs/Phase_Plan.md`)

## Phase

This PR implements part of: **Phase <number>** — <Phase Name>

Sub-phase(s): S<number>.<number> — <Description>

## Testing

Describe how you tested your changes:

- [ ] Unit tests added/updated in `tests/`
- [ ] Integration tests added/updated in `tests/integration/`
- [ ] GUI tests added/updated in `tests/gui/`
- [ ] Manual testing performed (describe below)

### Manual Testing Steps

1. Step one
2. Step two
3. Expected result

## Screenshots (if applicable)

| Before | After |
|--------|-------|
| ![before](url) | ![after](url) |

## Performance Impact (if applicable)

- Benchmark results: `scripts/bench.py --json`
- Memory impact:
- CPU impact:

## Breaking Changes (if applicable)

Describe any breaking changes and migration path:

## Additional Notes

Any other context, concerns, or questions for reviewers.