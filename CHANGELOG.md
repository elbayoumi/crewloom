# Changelog

## Unreleased

- `grid-safety` no longer flags fixed floors inside breakpoint-prefixed Tailwind grids that fit the breakpoint.
- Add a with/without-role evaluation on a seeded fixture (result: tie, inconclusive) to `documentation/EVIDENCE.md`.
- Add `pyproject.toml` (`pip install -e .` provides the `crewloom` command), `crewloom install --host claude|agents`, and `crewloom dashboard`.
- Add issue and pull request templates and an inline dashboard demo.
- Add the optional live web dashboard (`dashboard/`): role status, memory counts, tool runner, run feed, and repository checks with server-sent updates.
- Record every `crewloom.py run` to `.crewloom/runs.jsonl` (opt out with `CREWLOOM_NO_LOG=1`).

## 0.2.0 — 2026-10-01

- Restore 108 detailed, filtered source references across all 42 roles.
- Add nine domain tools, bringing the catalog to twelve local Python tools.
- Add CLI tool discovery and execution, six runnable examples, and workflow recipes.
- Expand regression coverage for frontend checks and delivery evidence.
- Rework English and Arabic entry points with a banner and direct paths to useful work.

## 0.1.0 — 2026-10-01

- Initial public role guides, clean memory, context packs, and repository gate.
