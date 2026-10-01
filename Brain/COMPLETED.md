# Completed work

### 2026-10-01 — Initial public toolkit
- Artifact: 42 English public role guides, clean memory, core CLI and checks.
- Impact: Independently usable repository edition without client history or external account configuration.
- Evidence: See the exact validation results in the release notes.

### 2026-10-01 — Public edition verification
- Artifact: `documentation/VALIDATION.json`.
- Impact: 19 core tests pass; 42 guides pass structure checks; English and Arabic context commands work.
- Evidence: Clean archive checks pass, public secret-pattern scan reports zero findings, bad commit rejected and clean commit accepted.

### 2026-10-01 — Public toolkit depth and presentation
- Artifact: 108 detailed references, twelve tools, six examples, workflow recipes and bilingual entry pages.
- Impact: Roles link to detailed procedures and applicable executable checks.
- Evidence: 52 regression tests pass, including all six published CLI examples.

### 2026-10-01 — Live dashboard
- Artifact: `dashboard/` (Next.js), `scripts/crewloom.py` run log, `scripts/test_run_log.py`.
- Impact: Roles, memory counts, tool runs, and repository checks are observable live; CLI runs appear in open tabs without reload.
- Evidence: 4 dashboard unit tests, typecheck and production build pass; API run, traversal rejection, and SSE change event verified against the running server.

### 2026-10-01 — Adoption path
- Artifact: `pyproject.toml`, `crewloom install/dashboard` commands, issue/PR templates, README GIF.
- Impact: Roles installable into a project in one command; dashboard starts with one command.
- Evidence: 3 install tests pass; editable pip install in a clean venv runs `crewloom tools`; `crewloom dashboard` served `/api/overview` 200.

### 2026-10-01 — First real-project evidence
- Artifact: `documentation/EVIDENCE.md`.
- Impact: Tools run on 3 internal projects; 2 findings measured and classified false positives, not hidden.
- Evidence: commands and browser measurements recorded in the file.

### 2026-10-01 — grid-safety breakpoint awareness
- Artifact: `.agents/skills/frontend-ux-auditor/scripts/check_responsive_grid_safety.py`.
- Impact: Removes the 2 measured false positives without hiding unprefixed or oversized floors.
- Evidence: 10 tests pass (4 new); code-vault re-run passes.

### 2026-10-01 — With/without role evaluation
- Artifact: `examples/evaluation/frontend-audit/`, section in `documentation/EVIDENCE.md`.
- Impact: First controlled comparison; result is a tie (9/9 both), recorded honestly as inconclusive.
- Evidence: ground truth written before runs; both reports scored against it.

### 2026-10-01 — palette-drift tool
- Artifact: `.agents/skills/frontend-ux-auditor/scripts/check_palette_drift.py` (+11 tests), registered as tool 13.
- Impact: Closes the gap where the playbook named a project-supplied check that did not exist; flags off-token colors with file:line.
- Evidence: on the seeded fixture it reports all 3 seeded off-token locations (#ff6600 x2, #ddd) plus #fff neutrals; real project code-vault passes (18 files).

### 2026-10-01 — Second with/without evaluation
- Artifact: `examples/evaluation/frontend-audit-v2/`, section in `documentation/EVIDENCE.md`.
- Impact: 3 runs per condition on a 20-defect fixture; recall tie (100%), role runs flagged 1/18 decoys vs 7/18, +15% tokens.
- Evidence: ground truth written before runs; per-run numbers in runs.json; graded non-blind by the runner.

### 2026-10-01 — Project path isolation
- Artifact: Project-scoped CLI logs/context and dashboard execution/memory.
- Impact: Project-relative inputs and isolated histories; cross-project paths rejected.
- Evidence: 75 Python tests, five dashboard tests and TypeScript checks pass.
