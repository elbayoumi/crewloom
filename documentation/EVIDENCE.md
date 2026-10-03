# Evidence log: tools run on real projects

Dated records of Crewloom tools run against real codebases, with commands, raw results, and what was and was not verified. Project names are internal RUMUZE products; no client code is included.

## 2026-10-01 — Frontend checks on three Next.js projects

Role: [frontend-ux-auditor](../.agents/skills/frontend-ux-auditor/SKILL.md). Commands (`{dir}` = project folder):

```bash
python3 scripts/crewloom.py run ui-hints -- --project-dir {dir} --json
python3 scripts/crewloom.py run grid-safety -- --project-dir {dir} --json
```

| Project | Files scanned | `ui-hints` | `grid-safety` |
| --- | --- | --- | --- |
| code-vault | 19 | 0 hints, exit 2 (rendered review required) | **2 flagged**, exit 1 |
| rumuze-mvp-boilerplate | 19 | 0 hints, exit 2 | pass |
| restaurant-cafe-base | 46 | 0 hints, exit 2 | pass |

`ui-hints` exits 2 by design: a static scan cannot accept a layout, so it asks for rendered review instead of claiming a pass.

### The two flagged grids

Both are in code-vault and use a fixed pixel floor in a column track behind the `lg:` prefix:

- `app/services/[slug]/service-detail-client.tsx:238` — `lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.85fr)]`
- `app/services/runs/[id]/run-client.tsx:180` — `lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]`

Verification: a headless Chromium replica of the same `grid-template-columns` (16 px side padding, 20 px gap) at the smallest width where `lg:` applies and at 1280 px.

| Grid | Viewport | Columns | Horizontal overflow |
| --- | --- | --- | --- |
| 238 | 1024 | 596 px + 376 px | none |
| 238 | 1280 | 754 px + 474 px | none |
| 180 | 1024 | 663 px + 309 px | none |
| 180 | 1280 | 837 px + 391 px | none |

**Conclusion: both findings are false positives.** The floor only applies from 1024 px, where a 320 px track plus gap fits. Limits of this check: it reproduces the grid alone, not the full page with its real content, and was not run in the live app (which needs a database).

### What this shows

- The tools run on real projects and finish in well under a second each.
- `grid-safety` flags any fixed floor, even behind a breakpoint prefix that already guarantees the width. Recorded as a follow-up in `Brain/ROADMAP_TODO.md`.
- No claim is made that the role improves an agent's output; that needs a controlled with/without comparison on the same task, which is still open.

### Follow-up: tool corrected

`grid-safety` now skips a fixed floor inside a Tailwind `sm:`–`2xl:` arbitrary grid class when the floors sum to at most half that breakpoint's width. Unprefixed floors, floors too large for their breakpoint, and other tokens on the same line are still flagged (4 new regression tests). Re-running the original command on code-vault now passes; the two findings above no longer appear. The half-breakpoint margin is a conservative rule of thumb, not a measurement of gaps or padding in a given page.


## 2026-10-01 — With/without the role on a seeded frontend (n = 1 run each)

Question: does giving an agent the `frontend-ux-auditor` role change what it finds? Setup: one small Arabic RTL React storefront ([fixture](../examples/evaluation/frontend-audit/fixture)) with 9 seeded defects and 3 correct "decoy" constructs, recorded in [ground_truth.json](../examples/evaluation/frontend-audit/ground_truth.json) before either run. Two subagents of the same model got the same task, each on its own copy, read-only:

- **A (no role):** generic instruction to review UI/UX, accessibility, responsive, RTL, token and security problems.
- **B (with role):** additionally told to read `AGENTS.md`, the role's `SKILL.md`, references and brain, and run `ui-hints` and `grid-safety`.

| | A: no role | B: with role |
| --- | --- | --- |
| Seeded defects found (of 9) | 9 | 9 |
| Decoys wrongly flagged (of 3) | 0 | 0 |
| Total findings reported | 21 | 18 |
| Seeded defects confirmed by a Crewloom tool | n/a | 2 (missing `alt`, unguarded grid floor) |
| Subagent tokens / tool calls / time | 67.8k / 3 / 36 s | 82.3k / 6 / 47 s |

**Result: no measurable difference in recall or precision on this fixture.** Both found every seeded defect and neither flagged a decoy. The fixture is too easy to separate them, and one run each cannot show a real effect either way, so this does not show that the role improves results.

What the role did change, from B's own report:

- Two findings were backed by a deterministic tool result (exit codes and line numbers) instead of only model reading.
- B added SEO/AEO and landmark findings drawn from the playbook (no meta description, client-rendered catalog); A added hardening findings (CSP, response validation, skip link). The extra findings were not scored against ground truth.
- B used about 21% more tokens and twice the tool calls.
- The role's own gaps surfaced: the playbook relies on a project-supplied `check_palette_drift.py` that is not included, so the seeded off-token colors were found by reading only, and the role's brain files are empty templates.

Next experiment needed to say anything stronger: several runs per condition, harder seeded defects that a generic review tends to miss, and a blind grader for the extra findings.

### Follow-up: `palette-drift` added

The gap found above (off-token colors reachable only by reading) is closed by the new `palette-drift` tool. On the evaluation fixture it reports `src/styles.css:5` and `src/App.tsx:39` (`#ff6600`) and `src/styles.css:4` (`#ddd`), the seeded off-token locations, plus `#fff` literals at `src/App.tsx:39` and `src/styles.css:7`, which are not in the tokens and can be accepted with `--allow`. On code-vault (18 source files, its own `design-tokens.json`) it passes. It checks hex and numeric `rgb()` literals only; contrast and rendering still need a browser.

## 2026-10-01 — Second with/without evaluation: harder fixture, 3 runs per condition

Fixture: [frontend-audit-v2](../examples/evaluation/frontend-audit-v2/fixture) — 10 files, **20 seeded defects** (7 reachable by Crewloom tools: two fixed grid floors, four off-token colors in different notations such as `#F60`, `rgb(255 102 0)` and a Tailwind `bg-[#ff6600]`, and a multi-line `<img>` without `alt`; 13 need reading: RTL, focus, labels, keyboard access, timer leak, unhandled fetch, key misuse, card logging, XSS) and **6 correct decoys**. Ground truth ([ground_truth.json](../examples/evaluation/frontend-audit-v2/ground_truth.json)) was written before any run. Per-run numbers: [runs.json](../examples/evaluation/frontend-audit-v2/runs.json). Conditions as before: A = generic review request, B = same request plus the `frontend-ux-auditor` role and its tools; three independent subagents each, same model, read-only.

| | A: no role (3 runs) | B: with role (3 runs) |
| --- | --- | --- |
| Seeded defects found | 20, 20, 20 of 20 | 20, 20, 20 of 20 |
| Seeded defects backed by a tool result | n/a | 7 of 7 tool-reachable, in every run |
| Decoys flagged (per run, of 6) | 4, 2, 1 | 0, 0, 1 |
| Decoys flagged, all runs | 7 of 18 | 1 of 18 |
| Findings reported per run | 38, 38, 32 | 27, 28, 19 |
| Subagent tokens per run (mean) | 71.8k | 82.9k (+15%) |

**Results**

- **Recall is a tie again (100% in all six runs).** A capable generic reviewer finds every defect in a 10-file project, so recall cannot separate the conditions here.
- **Fewer wrong change requests with the role:** 1 of 18 decoy opportunities versus 7 of 18. Caveats that limit this: n = 3 per condition, grading was done by the assistant that ran the experiment (not blind), and the decoys flagged most (`D2`, the breakpoint-prefixed grid floor that fits at `lg:`) are the case the tool was corrected for after the first evaluation, so that part is partly by construction. Excluding `D2`, A flagged 4 and B flagged 0, which is suggestive and far too small a sample to call significant.
- **Less padding:** B reported about a third fewer items per run (mean 25 versus 36). Extra items were not scored, so this does not show they were wrong.
- **Cost:** +15% tokens.
- **Prompt error on my side:** the B prompt suggested passing `--tokens` to every tool; `ui-hints` and `grid-safety` reject it, and all three B agents worked around it by omitting the flag. The tools were not at fault.

**What this does and does not show.** The role plus tools gave deterministic, line-accurate evidence for the 7 defects they cover and, in these runs, fewer unwarranted change requests. It did not find anything a generic reviewer missed. A claim that the role improves results still needs defects a generic review tends to miss, more runs, and a blind grader.

## 2026-10-01 — Project path isolation

75 Python regressions and five dashboard tests pass, including separate project histories and memory, identical relative input names, and cross-project path rejection. TypeScript `tsc --noEmit` passes. These are entry-point guards, not host sandbox evidence.

## 2026-10-01 — Isolated software execution and objective acceptance

The six-stage Unicode feature completed inside Docker using image `sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d`. Its five feature acceptance tests passed; resume did not repeat successful commands. Real Docker checks also exercised network denial, a foreign-project symlink, unmounted library/immutable runtime state, bounded output capture, and timeout termination. The command executor uses a 1 GiB memory limit, two CPUs and 128 processes.

The repository now has 100 Python test cases: 95 run in the standard gate; five live Docker cases are opt-in locally and mandatory in the separate CI job. Five dashboard tests pass. Editable installation in a fresh Python environment, workflow doctor, and installed-CLI role validation passed. Hosted results are recorded after push.

The objective Unicode grader was run three times per supplied implementation. Reference: 9/9 each time. Deliberately limited ASCII baseline: 5/9 each time. Expected answers stay outside the candidate container; the scorer receives no treatment/model labels. See [raw results](../examples/evaluation/unicode-slug/results.json). These fixtures validate scorer discrimination, not an improvement in agent-generated results. Actual cross-provider, independently coordinated with/without trials remain unperformed.

Release source secret scan: three raw detections, all verified as 64-character SHA-256 values in MANIFEST.json; no confirmed credentials. Runtime/build caches were excluded from the public source export.

## 0.5.0 — Model generation and repeated acceptance

The [model workflow execution](../examples/model-workflow/evidence.json) records a newly generated Codex implementation and five passing Docker tests, then successful resume without regenerating completed artifacts. A host diagnostic item was initially misclassified as a tool event; the parser now requires completed generation and distinguishes nonfatal diagnostics from tool execution. Regressions preserve that boundary.

The [trial evidence](../examples/evaluation/host-trials-20261001/README.md) contains five fresh Codex generations per condition (with/without full-stack role). All ten pass nine contract cases: a tie, not measured superiority. Two Claude generation attempts failed with no local authentication and eight remaining calls were blocked; no cross-host conclusion is available. Task and acceptance cases are public, scoring is deterministic and label-free, and the runner is also the coordinator. There is no independent human review claim.

All 42 roles now have English project procedures as well as source Arabic playbooks, for 150 detailed role references. Documentation/structure checks do not validate every external-domain workflow. Provider calls are excluded from ordinary CI.

## Automatic project context — integrated source, 2026-10-03

Runtime commit `8e83941` integrates with `main` at `a8dcff4`. Package metadata is 0.5.1; these checks do not assert a new release tag. Earlier measurements remain in [Brain/COMPLETED.md](../Brain/COMPLETED.md).

| Check | Execution | Result |
| --- | --- | --- |
| Repository and actual commit gate | `python3 scripts/check_repository.py`; hook enabled | 310 cases: 304 pass, 6 Docker-gated skips |
| Live Docker scripts | `CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p "test_*.py"` | 250 cases, all pass, zero skips |
| Independent acceptance boundaries | `python3 -m unittest discover -s scripts -p "test_context_acceptance_boundaries.py"` | 30 cases, all pass |
| Python 3.9 | Full repository gate in a Python 3.9 container with Git | 310 cases: 301 pass, 9 skips |
| Clean source archive | Full gate from extracted source without Git/runtime/build files | 310 cases: 304 pass, 6 Docker-gated skips |
| Public project pilots | English Crewloom and Arabic Paperclip UI; actual Docker executor | Nine fixed checks pass per project; verified finish and one acceptance attempt after repeat |

The baseline at `71da4ca` has 152 cases. This change adds 158 regressions. Known failing fixtures are rejected for forged or drifted executor evidence, foreign/copied bindings, cross-project ownership, stale ranges, context overflow, dropped declared inputs, uncancellable failed entry, and commit-hook Git environment leakage. A poisoned-Git fixture run leaves the unrelated repository's HEAD, index, configuration, refs and history unchanged; the actual commit also passed with the hook enabled.

The [public pilot contracts and results](../examples/evaluation/project-context-20261003/README.md) are reproducible. Selected context is 43,231 versus 187,358 bytes for Crewloom (76.93% fewer bytes), and 54,106 versus 22,705,265 for the scoped Paperclip UI (99.76%). Both retain whole declared input bodies, rules and acceptance criteria under the unchanged 131,072-byte ceiling. Both warm scans parse zero unchanged files. These are navigation/context checks, not application quality or universal billed-token savings.

The synthetic pilot executes acceptance in Docker and verifies finalization at both sizes: 8,179/10,724 bytes for 26 files and 16,911/1,438,664 bytes for 606 files. Dense optional-navigation reproduction retains 23 of 1,441 candidate ranges in 7,928 bytes under its 8,192-byte allowance; omitted hints are recorded. Required source bodies are never truncated to fit optional navigation.

The source-only Gitleaks 8.30.1 scan reports three heuristics, all reviewed as manifest SHA-256 values for design-token fixtures; no confirmed credentials. Native integration is instruction-assisted; automatic refresh applies to the managed lifecycle. Provider billing/answer-quality studies, private-client rollout after registry reconciliation, richer JS/TS alias resolution and verified host folder-open callbacks remain future work.

Publication: [PR #2](https://github.com/elbayoumi/crewloom/pull/2) contains the integrated implementation and these reproduction assets. The first [hosted run](https://github.com/elbayoumi/crewloom/actions/runs/37116755909) passed dashboard tests/type checking/build and isolated workflows/pilot/grader. The validate job correctly refused the absent default Docker image; its matrix now explicitly preloads that image, retaining every acceptance assertion. Consult the PR checks for the current hosted result.

The corrected [hosted run](https://github.com/elbayoumi/crewloom/actions/runs/37117271745) passed both Python versions, dashboard, isolated workflows and security checks on exact PR head `13b29e4`. [PR #2](https://github.com/elbayoumi/crewloom/pull/2) was merged into main as `d9e6c64` after those checks. Earlier pending/failure entries above are preserved as history.
