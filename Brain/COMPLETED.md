# Completed work

### 2026-10-18 — Zero-friction developer experience, Cursor/Windsurf MCP, and competitive positioning
- Artifact: `quickstart.sh`, `scripts/crewloom.py`, `examples/mcp/cursor.json`, `examples/mcp/windsurf.json`, `examples/mcp/README.md`, `README.md`, `README.ar.md`, `scripts/test_e2e_expansion.py`.
- Impact: Fast zero-install quickstart script (`./quickstart.sh`) with dry-run support; rich interactive ANSI CLI walkthrough (`crewloom demo`); official MCP configurations for Cursor and Windsurf (resolving Issue #40); 7-dimension competitive framework comparison matrix and vector architecture workflow diagrams in English and Arabic.
- Evidence: 93 strict E2E tests pass (0 skips, 0 failures) in `scripts/test_e2e_expansion.py`; repository gate passes cleanly with 0 errors (`check_repository.py`); MCP configuration schema verified across all templates.

### 2026-10-17 — Post-merge container isolation and acceptance hardening
- Artifact: `scripts/workflow.py`, `scripts/test_docker_command.py`, `scripts/test_host_lifecycle.py`, `dashboard/`.
- Impact: Workflow containers explicitly refuse execution under host root (UID 0); host lifecycle test fixtures fall back to supported version when system tools are upgraded; dashboard verified with clean 59/59 tests, tsc, and production build; REA pinned MCP probed against harmless fixture.
- Evidence: 9 docker command isolation tests pass including root refusal; 75 host lifecycle tests pass on unpinned host environment; dashboard builds in 1.6s with zero errors; remote PR #35 branch deleted after merge.

### 2026-10-17 — REA role and hardening
- Artifact: `.agents/skills/reverse-engineering-analyst/`, `examples/mcp/rea.json`, `examples/re/findings.json`, `dashboard/lib/child-env.ts`, `scripts/test_docker_command.py`.
- Impact: Reverse-engineering role with evidence bookkeeping; dashboard children no longer inherit the dashboard token; container isolation flags are regression-tested without Docker.
- Evidence: Required gate passes with the 43-role counts; 10 findings-checker, 8 isolation-command and 3 environment-hygiene cases pass. REA was not executed against a real target and the Chrome companion's `<all_urls>` scope is unchanged by design.

### 2026-10-15 — Hosted Python compatibility follow-up
- Artifact: native_desktop.py and its existing regression suite; PR21 first-head failure retained.
- Impact: synchronous construction needs no implicit event loop; asynchronous native operations serialize on one loop and reject foreign loops.
- Evidence: actual Python3.9 Docker and Python3.14 each9pass/1optional-live-skip; original hosted failure and new red/green construction test confirm the cause. Final gate/hosted rerun follows.

### 2026-10-15 — Professional repository review
- Artifact: documentation/PROFESSIONAL_REVIEW.md, launcher/tests, pinned CI and Dependabot configuration; prior defect-closure commits retained.
- Impact: explicit acceptance cannot skip missing prerequisites; first dashboard install obeys the lockfile; bilingual setup matches runtime behavior.
- Evidence: required commit gate99 suites/1216cases (1104pass/112skip); dashboard56, browser41pass/1skip, MCP9pass/1skip, capture8, distribution14 and Docker34/43 pass; TypeScript/build and npm audit clean. Hosted outcomes belong to the reviewed commit.

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

### 2026-10-01 — Role installation memory isolation
- Artifact: Memory-preserving role updates and clean first-install project records.
- Impact: Library history is not imported; force updates retain local experience.
- Evidence: Existing install regressions now exercise retained memory and nested destination symlink rejection; full gate passes.

### 2026-10-01 — Executable software workflows
- Artifact: Isolated workflow runner, six-stage feature/task plans, objective grader and six English role contracts.
- Impact: Executable project work, persistent attempts/handoffs and verified command boundaries.
- Evidence: 100 Python cases covered across core/live-Docker suites; five dashboard tests; fresh editable install; reference 9/9 and seeded baseline 5/9 in three grader runs.

### 2026-10-01 — Bounded model generation and English role depth
- Artifact: CLI model adapters, generated-feature example, provider trial harness and 36 additional English specialist procedures.
- Impact: Explicit project inputs/outputs, checked generation, all 42 English procedures and reproducible scoring.
- Evidence: Codex feature passes five live Docker tests; ten fresh trial submissions tie at 9/9. Claude has two authentication failures/eight skipped calls; cross-host evaluation incomplete.

### 2026-10-01 — Self-Editing Mode naming
- Artifact: `documentation/SELF_EDITING.md`, constitution and improvement-role entry point.
- Impact: Owner-selected English/Arabic name activates the existing in-place maintenance workflow.
- Evidence: Role ID preserved; documentation explicitly distinguishes host task activation from CLI/background execution.

### 2026-10-02 — Managed enforcement
- Artifact: declared-file execution broker, tool-free provider gateway, default native CLI rejection and enforcement guide.
- Evidence: repository gate covers 139 cases (133 pass, six Docker cases skipped); live broker suite passes all six cases. Live provider authentication is unverified because API keys are not configured.

### 2026-10-02 — Context efficiency
- Artifact: bounded memory selection and context-aware reuse. Evidence: 25 model-host regressions pass; synthetic full/focused prompt 63,107/9,439 bytes (85.04% smaller). No live token-cost or quality claim.

### 2026-10-02 — Repository navigation
- Artifact: crewloom map CLI, project-local cache, bounded ranking and model opt-in. Evidence: seven map regressions; local 55-file scan renders 4076 bytes and second scan reuses 55 parses. No live token/latency claim.

### 2026-10-02 — Automatic context implementation plan
- Artifact: documentation/AUTOMATIC_PROJECT_CONTEXT_PLAN.md. Evidence: reviewed current map, model prompt, workflow and agency project-control/context binding; documentation structure/link check passes. Automatic lifecycle remains proposed.

### 2026-10-02 — Automatic project context implementation
- Artifact: `crewloom.project.json` plus `.crewloom/{binding,index,context,tasks,lessons}`; `scripts/project_binding.py`, `scripts/project_context.py`, `scripts/project_lessons.py`, `scripts/context_pilot.py`; in-place `repo_map.py` upgrade; managed enter/checkpoint/publish-gate/finalize in `scripts/workflow.py`; `crewloom project` and `crewloom lesson` commands; `documentation/PROJECT_CONTEXT.md`.
- Impact: opt-in project identity and checkout binding, safe idempotent bootstrap, explicit relocation, frozen per-task context with hash-validated ranges, executor-gated lesson promotion, and an agency ledger adapter that reuses the existing project-control contract instead of a second client list. Workflow reservations, artifact broker, provider defaults and model CLI opt-in are unchanged.
- Evidence: the draft measurements below were superseded by the corrected entries that follow; they are preserved as history.

### 2026-10-02 — Draft automatic project context evidence (superseded)
- Evidence: repository gate 251 cases (245 pass, 6 Docker skips); measured 64 indexed files / 391856 source bytes; synthetic pilot 62.6% / 0.92% selected share. Independent review later reproduced real defects in this draft, so these numbers are not final acceptance.

### 2026-10-02 — Independent automatic-context acceptance review
- Artifact: `scripts/test_context_acceptance_boundaries.py` and two frozen public-repository navigation pilots.
- Evidence: Docker executed all nine navigation checks in each English/Arabic pilot; the independent suite reached 5 pass / 5 fail on the draft.
- Limit: preliminary context/navigation checks only; they are not application build quality or final lifecycle proof.

### 2026-10-02 — Corrected automatic project context
- Artifact: process-scoped project lock ownership, byte-room-bounded optional context records, semantic-only generation fingerprints, immutable generation history, executor-outcome correlated lesson promotion, scoped index inventory for freshness, and frozen-context delivery inside the managed model prompt.
- Impact: unchanged work reuses its generation instead of incrementing; dense fan-out projects stay inside the frozen byte budget without dropping declared bodies; forged or drifted evidence can no longer promote a lesson; a rejected task writes nothing; the managed prompt now carries the frozen scope, complete governing rules, verified remedies and the immutable semantic SHA the gate accepted.
- Evidence: repository gate 287 cases (281 pass, 6 Docker skips), 135 new regressions against the independently measured 152-case baseline at 71da4ca; live Docker `CREWLOOM_DOCKER_TESTS=1` scripts suite 227/227; Python 3.9 container gate passes with 9 skips. This checkout: 65 indexed files / 473895 source bytes, cold parse 159 ms, warm reuse 72 ms with 0 parses, 8123-byte rendered map. Synthetic pilot executed its acceptance command inside the isolated Docker executor over six declared inputs and verified finalization for both sizes; selected context is 76.1% of full context at 26 files and 1.17% at 606 files. A 2002-indexed-file scoped reproduction produced a 16,663-byte context under the 131,072-byte budget with the declared body and seed intact.
- Limits: live provider tokens, cost and answer quality remain unmeasured; host folder-open callbacks are unverified; JS/TS package, alias and re-export resolution is a deferred adapter; the two authorized real-project pilots and final archive/release checks remain with the supervising agent.

### 2026-10-02 — Bounded optional ranges and exactly bound consumed evidence
- Artifact: decoder-aware scan accounting and pre-read refusal for oversized required bodies in `project_context.snapshot`; `budgets.range_bytes` plus a 64-record cap for suggested ranges; per-step `context_generation`/`context_semantic_sha256` binding resolved from the immutable archive; instruction block written before the freeze with shell-quoted exit evidence; navigation delivered in the managed prompt; managed map requests bound to project scope; entry-time lesson revalidation; explicit cancellation of a reserved but unstarted managed run.
- Impact: a large ceiling no longer fills itself with unrelated symbol hints; each completed model step re-verifies against the exact generation it consumed; first native entry no longer invalidates its own frozen instructions; an unreadable file can no longer buy unbounded scan bytes; a stale verified remedy cannot survive an entry.
- Evidence: repository gate 298 cases (292 pass, 6 Docker-gated skips); live Docker `CREWLOOM_DOCKER_TESTS=1` scripts suite 238/238 with 0 skips; independent boundary suite 27/27. Local dense reproduction (121 seed-related test files, 200 importers, 16.8 KB rules, 131072-byte ceiling): 1441 candidate ranges, 23 kept / 7928 bytes inside the 8192-byte allowance, 1418 recorded omissions, 44,729-byte snapshot, snapshot+rules+sources assembly 61,618 bytes; with the allowance removed the same fixture is refused at 131,137 bytes.
- Limits: this dense case is a local reproduction, not the authorized real project; the supervising agent still owns the Arabic/English and Paperclip reruns, the Python 3.9 gate, archive/manifest verification and any provider measurement.

### 2026-10-03 — Reproducible repeat measurement of identical context
- Artifact: `normalized_payload`/`stable_payload` in `scripts/context_pilot.py`, reported as `stable_sha256`, `stable_semantic_sha256` and `volatile_bytes`; corrected `test_repeat_measurement_of_the_same_size_is_identical` plus the deterministic `test_forced_recorded_timing_changes_measured_bytes_and_nothing_else` in `scripts/test_context_pilot.py`.
- Impact: a repeat measurement of the same project size is compared by exact payload equality over everything except the checkout's own identity and the recorded scan timing, while `selected_bytes`/`serialized_bytes` remain the actual recorded sizes; the raw size difference is accounted for exactly instead of tolerated as slop.
- Evidence: controlled reproduction of the reported flake (first/second byte delta 1 with equal root lengths, `telemetry.duration_ms` 120 vs 72); three live pairs show zero remaining differences after normalization with genuinely differing `semantic_sha256`; forced timings 9 and 1234567 resealed through `project_context.seal` give exact 6665/6671 bytes, stable payload and semantic digests equal and volatile byte delta exactly 6; negative controls (changed body text, moved range start) still reject. Focused pilot suite 7/7; independent boundary suite 27/27 unchanged; scripts suite 239 cases (233 pass, 6 Docker skips), giving 299 total cases with the 60 role-core cases, exit 0.
- Limits: Python 3.9 is not installed on this host now, so 3.9 coverage is an `ast` grammar check (`feature_version=(3,9)`) of both edited files rather than a second interpreter run; the supervising agent's earlier 3.9 gate predates this change. Docs, manifests and the pilot report archive remain with the supervising agent.

### 2026-10-03 — Commit-hook Git isolation for project discovery and fixtures
- Artifact: `git_environment`, `git_dir_for` and `require_git_root` in `scripts/repo_map.py`, used by every Git child (`git`, `git_optional`, `git_state`); repository-root binding before any cache write; the same cleared environment in the `scripts/test_*.py` repository fixtures and in `context_pilot.synthetic_project`; eight regressions in `scripts/test_repo_map.py`, including a source-level check that refuses any fixture starting Git without an explicit environment; the isolation contract in `documentation/REPOSITORY_MAP.md`.
- Impact: a commit hook's `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, object-store and `GIT_CONFIG_*` overrides can no longer bind discovery to the committing repository; the selected root must own the work tree, so a nested directory, a bare repository and a plain directory are refused instead of mapped, while author/committer identities, `PATH`, locale and time zone survive. Linked worktrees map as their own root, which is this checkout's own layout.
- Evidence: reproduction against a throwaway repository that exported the hook variables reported 30 failures and 8 errors across 242 cases and left a leaked `first` commit plus a `feature` branch in it, matching `HOOK_GIT_ENV_INCIDENT.json`; after the fix the same suite reports 250 cases, 0 failures, 0 errors, 6 skips with that repository's HEAD, index, configuration, refs and history byte-identical and its pending work still untracked. The same hook environment pointed at this real worktree maps 67 files at branch `codex/automatic-project-context`, head `71da4ca`, with the worktree HEAD/index/gitdir/commondir and the main repository configuration unchanged. The independent boundary suite is 30/30, the focused map suite 30/30, and `python3 scripts/check_repository.py` exits 0 with 310 cases (304 pass, 6 Docker-gated skips), the same 250-case scripts suite under the hook environment.
- Limits: this is an input guard on the environment Crewloom itself controls, not an OS sandbox, and a checkout whose work tree is configured elsewhere in `.git/config` is refused rather than followed. Python 3.9 is not installed on this host, so 3.9 coverage is an `ast` grammar check (`feature_version=(3,9)`) of the nine edited files rather than a second interpreter run; the supervising agent's earlier 3.9 gate predates this change. The actual commit, the public PR and the archive/manifest reconciliation remain with the supervising agent, and no commit or push was made here.

### 2026-10-01 — Precise concurrent project scope
- Artifact: Explicit workflow project selection, paused-task reservation, cancellation and concurrency regressions.
- Impact: Separate roots run together; one root cannot switch workflows while a manual task is outstanding.
- Evidence: Same-root concurrent invocation rejected; different roots with identical filenames run simultaneously; copied/symlinked reservations rejected and cancellation retains files/history.

### 2026-10-03 — Integrated automatic-context publication checks
- Artifact: Automatic context implementation `8e83941`, reconciled with main `a8dcff4`, public frozen pilot fixtures and final evidence/manifest.
- Impact: Bound project identity, incremental maps and executor-verified local lessons are available through managed lifecycle; native entry remains instruction-assisted.
- Evidence: Actual commit hook 310 cases (304 pass, 6 skips); post-integration live Docker scripts 250/250; actual Python 3.9 gate 310 (301 pass, 9 skips); clean source archive gate 310 (304 pass, 6 skips); independent boundaries 30/30. English/Arabic public pilots each pass nine frozen checks, repeat one acceptance attempt, and verify one local lesson.
- Limits: Provider bills and general answer quality unmeasured; no private-client rollout, no new release tag. GitHub checks and publication recorded separately after push.

### 2026-10-03 — Reviewable automatic-context publication
- Artifact: https://github.com/elbayoumi/crewloom/pull/2 at integrated head `4df2eae`; full implementation, public evidence and manifest uploaded without private client data.
- Evidence: Final 609-file source archive has 608 verified file hashes; fresh editable installation reports 0.5.1 and installed CLI role validation/project status pass. Hosted dashboard and isolated-workflow jobs pass on the first run.
- Limits: Hosted validate requires explicit default image preload; corrected in the existing matrix without removing tests. Current hosted result is visible on the PR; no new release tag asserted.

### 2026-10-03 — Automatic project context merged
- Artifact: PR #2 merged into public main at `d9e6c64` after exact head `13b29e4` passed every hosted check.
- Evidence: https://github.com/elbayoumi/crewloom/actions/runs/37117271745 — Python 3.9/3.14 validation, dashboard tests/type checking/build, actual Docker workflows/pilot/grader and GitGuardian all pass. Actual commit hooks remained enabled; source manifest and archive checks pass.
- Limits: No private-client rollout or new release tag; provider billing/quality and native callbacks remain deferred.

### 2026-10-03 — Phase A: installable distribution, authenticated dashboard, verified reviewers
- Artifact: `pyproject.toml` `0.6.0.dev0` with `MANIFEST.in`; `scripts/crewloom_resources.py`; `scripts/reviewer_credentials.py`; `dashboard/lib/auth.ts` with `app/api/auth/{login,session}/route.ts` and guards on `overview`, `skills/[id]`, `run`, `check`, `events`; `dashboard/test/auth.test.ts`, `dashboard/test/routes.test.ts`; owner-only delivery in `scripts/crewloom.py`; `scripts/test_packaging.py`, `scripts/test_distribution.py`.
- Impact: `list`, `show`, `validate`, `install`, `context`, `run`, `project`, `workflow` and `reviewer` all work from an installed wheel outside the checkout; the sdist carries the approved public source including `Brain/`, `MASTER_BRAIN.md`, `.github/`, `.githooks/` and the referenced demo assets, and never `.crewloom`, `node_modules`, builds or logs. Every dashboard API route and the event stream require authentication, the generated secret never reaches standard output, and a reviewer's issuance authority moved out of a trackable project file into protected runtime state that refuses inappropriate permissions.
- Evidence: `python3 scripts/check_repository.py` exits 0 with 357 cases (334 pass, 23 opt-in skips); opt-in `CREWLOOM_DISTRIBUTION_TESTS=1` distribution suite 11/11 with a real wheel and sdist built in a fresh venv and installed outside the checkout; the supervisor's independent credential and dashboard-path acceptance suite 11/11; the supervisor's independent dashboard acceptance suite 8/8; dashboard `npm test` 29/29, `tsc --noEmit` clean and `next build` clean. Rebuilding the sdist with the supervisor's isolated build frontend and running `check_repository.py --skip-tests` on the extracted archive now exits 0, where it previously reported six broken links.
- Limits: No browser or live-HTTP verification was performed here; the supervising agent owns that, plus the final wheel-from-sdist acceptance rerun, hosted CI and publication. `version = "0.6.0.dev0"` is development metadata, not a tag or a published release. Session revocation and the reviewer registry are per-process or per-owner integrity boundaries, not an OS sandbox against the project owner, and on a platform without POSIX permission bits the registry mode cannot be verified. Credential possession still does not prove a distinct human reviewed the work. No commit or push was made here.

### 2026-10-03 — Phase B3: recoverable grouped artifact publication and safe lock reclamation
- Artifact: `scripts/execution_policy.py` (`publish`, `recover`, `_validated`, `_abandon`, `_discard`, `_pending`); `scripts/workflow.py` (`_owned_claim`, `_discard_claim`, `_claim_reclamation`, `_release_reclamation`, `_reclaim`, `_execute` recovery); `scripts/project_binding.py` (`reconcile_publications`, `enter`); `pyproject.toml` (`js_syntax` flat module, `crewloom[syntax]` extra); `scripts/test_execution_policy.py`, `scripts/test_project_lifecycle.py`, `scripts/test_packaging.py`; `documentation/ENFORCEMENT.md`, `EXECUTION.md`, `ARCHITECTURE.md`, `TOOLS.md`, `RELEASE.md`.
- Impact: One declared output group publishes as one recoverable transaction held under the project lock for the whole publication and its recovery; a failed group is rolled back only after every journal record is proven restorable and keeps a bounded receipt instead of pending residue; an interrupted group is reconciled before project entry writes anything and before a workflow run reads state, freezes context, evaluates a gate or records acceptance; a foreign edit blocks reconciliation with the journal kept. Root-lock reclamation no longer follows symlinked claim, owner or lock paths and never recursively deletes claim contents. `js_syntax` is packaged, and the optional syntax extra pins the verified grammars.
- Evidence: The supervisor's independent lock acceptance suite 3/3 (its third case failed before this work with `FileNotFoundError` on the foreign `keep.txt`) and grouped-publication acceptance 6/6; all 8 recorded immutable test files byte-identical. Own broker suite 19 cases, 17 pass with 2 opt-in Docker skips, plus real container execution of a three-file group on `python:3.14-slim` reporting Python 3.14.7 in 405 ms with one committed receipt. Managed lifecycle suite 13/13 including recovery before context entry and refusal before any context write. `python3 scripts/check_repository.py` exits 0 with 348 cases (303 pass, 45 opt-in skips under plain `python3`; 18 skips with the pinned grammar interpreter). `python3 -m build` produces wheel and sdist; opt-in `CREWLOOM_DISTRIBUTION_TESTS=1` suite 11/11; both archives carry `js_syntax.py`, 42 roles and zero `.crewloom` entries, and metadata declares `Provides-Extra: syntax` with the three exact pins. All four changed modules parse under the 3.9 grammar.
- Limits: Python 3.9 itself is not installed on this host, so 3.9 was verified by grammar feature version rather than by execution. Grouped publication is recoverable, not an instant multi-file atomic filesystem change; a reader that ignores the project lock can still observe a group half applied, and that is documented rather than claimed away. Reclaiming a lock still does not stop a command or container that outlived the process that recorded it. Concurrent task coordination with worktrees, reviewed integration, native host lifecycle adapters, the controlled live usage/quality/latency study and rollout readiness remain Phase B2/C and are not started by this entry. No commit or push was made here.

### 2026-10-04 — Phase B2: concurrent worktree coordination with reviewed integration
- Artifact: `scripts/task_coordinator.py` as a flat runtime module (`validate`, `load_plan`, `topological`, `start`, `run`, `status`, `cancel`, `prepare`, `review`, `publish`, `_materialise`, `_execute_task`, `_verify_execution`, `_recheck_verified`, `_commit_outputs`, `_revalidate_publication`, `_verify_decision`, `main`); `crewloom coordinator` dispatch in `scripts/crewloom.py`; `pyproject.toml` flat module list; `scripts/test_task_coordinator.py`; `documentation/COORDINATOR.md`, `COORDINATOR.ar.md`, `COORDINATOR_ACCEPTANCE.json`, plus `ARCHITECTURE.md`, `ENFORCEMENT.md`, `EXECUTION.md`, `PROJECTS.md`, `EVIDENCE.md`, README navigation and the code registry; a `coordinator` CI job and a focused macOS `case-insensitive-paths` job.
- Impact: a project-local manifest DAG runs as a real batch — one Git worktree per task under the project's `.crewloom`, at most four concurrent managed executors, verified ancestor commits merged into a dependent worktree before it runs, and only verified declared outputs committed. The root is held with the same reservation a managed workflow writes, so ordinary workflow and native-context writers refuse it in both directions, and batch ownership is a kernel-held advisory lock so a second controller is refused and an interrupted one is provably gone without guessing a PID. The checked-out tree moves only by one recorded `--ff-only` fast-forward of a reviewed candidate after the manifest, binding, every task commit, output hashes, criteria, integration head, diff digest, credential and revocation, root HEAD, tracked cleanliness and untracked collisions are revalidated, and a consumed review decision cannot be replayed.
- Evidence: real batch on `python:3.14-slim` — three tasks, `workers: 2`, recorded overlapping intervals, three distinct local checkout bindings under one portable project ID, one recorded executor attempt per command step, a dependent task that read its integrated ancestors, a combined acceptance reporting `combined_acceptance: true` for all three artifacts, and a root fast-forward equal to the reviewed candidate with all worktrees retained; recorded in `documentation/COORDINATOR_ACCEPTANCE.json`. Own suite `scripts/test_task_coordinator.py` 36 cases: 23 pass offline in 8.9 s with 13 opt-in Docker skips, and all 36 pass in 45 s with `CREWLOOM_DOCKER_TESTS=1`. Supervisor's independent coordinator preflight suite 8/8 and read-only suite 1/1; the latter independently found that `git diff` rewrites `.git/index`, fixed by comparing with `git status --porcelain` under `GIT_OPTIONAL_LOCKS=0`. Filesystem alias suite 5/5 on this actual case-insensitive host. `python3 scripts/check_repository.py --skip-tests` exits 0 with the new guides and links.
- Limits: no model produced any artifact here, so this proves orchestration, isolation, dependency integration, combined acceptance and reviewed publication rather than model-generated code quality, and no provider call was made. Batch ownership needs POSIX advisory locking and is refused elsewhere rather than guessed. Reclaiming ownership does not stop a container that outlived its controller, and the coordinator terminates nothing it does not own. Only command steps run; a `model` or `task` step needs a provider policy or human review decision the coordinator deliberately does not grant. Declared-label review names a reviewer without authenticating one, a credential proves key possession only, and both are documented as such. Publication is one Git fast-forward subject to Git's own atomicity limits, not a reset, history rewrite, push or GitHub merge; untracked files are never cleaned. Native host adapters, the controlled live study, the curated public example and rollout readiness remain later phases. Python 3.9 execution is still unverified on this host. `check_repository.py` currently times out its `scripts` directory at 60 s while the whole combined `scripts` suite needs about 221 s on this host, so the full gate needs a supervising decision about that budget. No commit or push was made here.

### 2026-10-04 — Independently verified readiness and native transport boundaries
- Artifact: read-only agency readiness, protected `.crewloom/readiness/` reports, OpenCode usage normalization and complete-response checks, and coordinator read-only Git preflight.
- Evidence: readiness 15 independent cases pass on macOS; actual Python 3.9 readiness 37/37 and transport/legacy generation 70/70 with no skips. The OpenCode native opt-in regression now rejects generation before provider access or output publication. Correct context-study references pass all 33 frozen cases in real Docker.
- Limits: three independent grader integrity cases still reject the current implementation; native lifecycle callbacks, concurrent model-step integration, complete development example, live 36-call comparison and final distribution/publication remain in progress. Current proofs do not establish token savings or private-client rollout.

### 2026-10-04 — Verified concurrent model workflows and controlled grader integrity
- Artifact: model steps in isolated coordinator worktrees, explicit committed and per-run native opt-in, and typed held-out grading with a read-only Docker mount.
- Evidence: independent parent execution passes 14 coordinator cases, including four real Docker model-workflow cases with provider transport mocked; actual Python 3.9 coordinator suite passes 42 cases with 17 explicitly Docker-gated skips. Ten independent real-Docker grader checks pass, including all 33 correct reference cases, checker chmod/write rejection, input mutation on normal/error paths and returned-error/custom-exception rejection.
- Limits: synthetic stand-ins prove orchestration and acceptance, not model quality. The live 36-trial study, native host callback pilots, full development example and final integrated publication remain pending.

- 2026-10-04 | Native adapters: 20 independent offline cases passed; controlled grader: 10 independent real-Docker cases passed, including all 33 correct-reference cases. Dashboard: 30 tests and production build passed. Actual native production pilots and 36 provider study trials remain pending.

### 2026-10-05 — Native delivery and same-batch recovery
- Artifact: Codex production callback pilot and concurrent development example.
- Impact: actual Codex received the context-only marker and verified configured acceptance in Docker; the app suite passes 37/37 with real Docker and same-project/same-batch native permission retry.
- Evidence: independent gate passed 769/834 cases with 65 explicit skips before the final native payload fixes; actual provider application and study remain pending.

### 2026-10-05 — Globally exposed editable CLI
- Artifact: user-local pipx editable installation of Crewloom 0.6.0.dev0 with Python 3.14.7, using the pip backend.
- Impact: the `crewloom` command is available on the existing shell PATH and follows this development checkout.
- Evidence: `crewloom --help` and `crewloom tools` both exit 0 from outside the checkout; pipx metadata confirms editable mode. This installation does not complete pending production acceptance.

### 2026-10-05 — OpenCode context injection fixed; frozen study run recorded
- الملف: `adapters/opencode/crewloom-lifecycle.js`, `scripts/test_opencode_system_inplace.py`, `examples/evaluation/context-study-20261005.json`
- الأثر: real OpenCode 1.18.32 now receives injected context (receipt echoed, attempt7); the old `output.system = concat` reassignment ran the hook but delivered nothing. New 7-case test rejects the old line (6 fail) and passes the fix.
- ملاحظة: Codex 0.155.1 receipt, correct deny reason and allowed edit verified; study: 36 rows, Codex 17 scored, OpenCode 0 scored, selected-map 0/11 on all 8 scored Codex trials — no savings claimed.

### 2026-10-05 — Independent application removed; repository scope gate enforced
- الملف: `REPOSITORY_SCOPE.json`, `scripts/check_repository.py`, `documentation/REPOSITORY_SCOPE.md`
- الأثر: an unrelated Android application (1,911 paths) that reached `main` is removed from the tree and now lives in its own private repository with history preserved; the gate rejects unregistered top-level names (known violation refused, clean tree accepted, also from an sdist-installed copy).
- ملاحظة: the old commits stay in public Git history; no rewrite was done. Gate verified on Python 3.9 and 3.14, Docker suites and a wheel built from the sdist (30/30).

### 2026-10-05 — Context study v1 failure diagnosed; v2 map designed
- الملف: `documentation/CONTEXT_STUDY_V2_DESIGN.md`
- الأثر: replaced an unverified guess with the verified cause (relative `from .money import` in all 8 selected-map modules vs `from src.money import` in all full-source modules; helper bodies were present). Designed a closure map plus an offline sufficiency gate that would have rejected v1 before any call.
- ملاحظة: design only, no runtime change or provider call; corrected the wrong cause in the public record, CHALLENGES and ROADMAP.

### 2026-10-05 — Study v2 closure map implemented behind frozen tests
- الملف: `scripts/repo_map.py`, `scripts/evaluate_hosts.py`, `scripts/test_study_closure_map_boundaries.py`
- الأثر: closure-map arm, v2 plan (seed 20261006, 18 Codex trials) and an offline gate that rejects the v1 selected-map prompt for all 3 tasks and accepts full-source and closure-map; prompts 11.2–11.5 KB vs 20.8–20.9 KB full source.
- ملاحظة: 29 frozen cases pass (baseline 3/29), existing repo_map/study/Docker suites unchanged, Python 3.9 verified; no v2 provider call made, so no quality or saving claim.

### 2026-10-06 — Study v2 runner implemented behind frozen tests
- الملف: `scripts/evaluate_hosts.py`, `examples/context-study/grader/references/`, `scripts/test_study_v2_runner_boundaries.py`
- الأثر: `--study-v2` runs the 18-call closure-map study with a pre-call sufficiency gate and frozen references; v1 record unchanged. A gate failure creates no directory and makes no call.
- ملاحظة: 21 frozen cases pass (baseline 2/21); no v2 provider call made yet.

### 2026-10-06 — Post-run verification of frozen study inputs
- الملف: `scripts/evaluate_hosts.py`, `scripts/test_study_v2_verification_boundaries.py`
- الأثر: closes review gap P1 — every frozen digest is recomputed after the last trial, a mismatch refuses the report and is named; v2 limits no longer describe the v1 arm (P2).
- ملاحظة: 11 frozen cases pass (baseline 2/11); v1 limits and record unchanged; Docker suites unchanged.

### 2026-10-06 — Study v2 run completed (Codex, 18 calls)
- الملف: `examples/evaluation/context-study-v2-20261006.json`
- الأثر: closure-map 99/99 held-out checks = full-source 99/99, input tokens 12,194 vs 14,941 mean (2,731–2,767 lower in all 9 pairs, ~18%); gate passed before the run; the verifier recorded 31 named inputs, all unchanged after the last trial (`inputs_verification` in the record).
- ملاحظة: ceiling effect, no cost reported, uncached tokens and latency show no reliable difference, one host and three tasks; no wider claim.

### 2026-10-06 — OpenCode schema statement (14 refused generations diagnosed)
- الملف: `scripts/model_host.py`, `scripts/test_opencode_schema_prompt_boundaries.py`, `scripts/test_host_prompt_budget.py`
- الأثر: cause verified from stored outputs (13 flat maps + 1 `{"files":…}`, shape never stated to OpenCode); schema now stated in the agent's system prompt, study prompt untouched, invented shapes still refused.
- ملاحظة: 16 frozen cases pass; first design (append to the prompt) was rejected by the existing frozen isolation test and replaced; real-model check pending, the 4 ~300 s timeouts are a separate open cause.

### 2026-10-09 — Project catalog and actionable monitoring
- Artifact: explicit disjoint-root catalog, project setup and authenticated project/task panel.
- Impact: no guessed project selection; stale identities are unavailable; cancellation retains files and affects only the selected root.
- Evidence: 17 catalog cases, 37 dashboard cases, TypeScript, full repository gate and 49 live-Docker coordinator cases passed; real browser cancellation left the second fixture active.
- Evidence: isolated wheel install/setup/registration passed outside source; mobile RTL viewport/document widths both 390px.

### 2026-10-09 — Remove local dashboard password
- Artifact: local launcher/access mode and direct-opening dashboard.
- Impact: no sign-in field, no generated token and no logout control in local mode.
- Evidence: 38 dashboard cases and 10 public-core cases pass; new browser reports zero password fields/sign-in buttons, session method local; foreign-Origin mutation returns 403.

- 2026-10-09: Fixed PR #10 listener-coupling review: actual loopback listener required. Dashboard tests (38), TypeScript and live /api/auth/session verified local authentication.

### 2026-10-10 — Scheduling, shared admission and measured activity
- Artifacts: task_queue.py, usage_budget.py, bilingual_evaluation.py and activity panel. Evidence: 14 shared-admission cases including real Docker across two worktrees; two independent queued projects verified in real Docker; 39 dashboard cases and TypeScript pass; real grader accepted 40 reference cases and rejected incorrect/mutating candidates. Live multi-host pilot scored 3/12 planned trials (Codex 61/61 held-out cases); unavailable hosts and one Codex transport failure retained.

### 2026-10-11 — Source-linked user context
- Artifact: `scripts/user_context.py`, frozen-context/model-prompt integration and `documentation/USER_CONTEXT.md`.
- Impact: Explicit user/task selection, preserved corrections, quoted statements versus assumptions, stale-source and ambiguity rejection.
- Evidence: 14 regressions pass, including Arabic managed/native payload delivery and owner-only frozen copies, copied-project rejection and source changes. General model-quality improvement remains unmeasured.

### 2026-10-11 — Private data and selected publication
- Artifacts: `scripts/privacy.py`, automatic user-source hook setup, role-memory ignore rules and `documentation/PRIVACY.md`.
- Impact: Forced private additions blocked, original sources registered, prior hooks preserved and selected ZIP packets owner-only.
- Evidence: Real bad commit rejected and clean commit accepted; user-context 14 cases, installation 6 cases, binding 38 cases and repository-gate 20 cases pass. Privacy-specific regressions: 14 cases cover the private commit/publication boundaries. No history rewrite, repository-visibility change or universal secret detection claimed.
- 2026-10-11 | Coordinator privacy compatibility: isolated task worktrees seed missing role memory without copying private root lessons; real scope-hook fixture includes privacy dependencies.
- 2026-10-11 | Privacy acceptance: 15 regressions include clean/private commits in an independently bound linked worktree; 49 coordinator cases (17 optional skips), 29 scope and 11 real distribution cases pass.
- 2026-10-11 | Review fixes: moved checkout rebind re-homes the owned guard and prior-hook paths; ordinary ignore additions stay unchanged. 17 privacy regressions pass, including clean/private commits after relocation.

- 2026-10-11 | CSS privacy dependency fix: PostCSS 8.5.29 override/lock; known outside-map read is rejected by the new regression (fails with 8.4.31, passes patched). Dashboard 40 tests and production build pass; npm audit reports zero known vulnerabilities.

- 2026-10-11 | Inherited guard reuse: 18 privacy cases pass; repeated parallel setup preserves shared hooksPath and clean commits, while recording an original source in the worktree blocks its commit.

- 2026-10-11 | Understanding protocol preparation: eight bilingual synthetic scenarios, two arms, pinned fixture, strict grader and installed CLI contract verification. Nine evaluator tests (one optional Docker skip) exercise 64 single-field corruptions plus malformed responses; 14 user-context regressions pass after selector reuse. Live collection/model improvement remains unmeasured.

- 2026-10-11 | Fixed two reproduced statement-loss cases: later same-key or task-specific hypotheses no longer erase quoted statements; same-kind corrections preserve correct supersedes links. Sixteen user-context cases pass, including managed/native delivery of both kinds. Understanding preparation explicitly refrozen before any model trial: nine scenarios (36 planned trials/host), corrected request-intent/missing-language labels, 72 single-field corruptions plus malformed responses rejected. Live quality comparison remains pending.

- 2026-10-11 | Understanding input preflight: independently audited required source IDs, exact bilingual quotes, authoritative scope/request and selected user/task isolation checked before offline verification. Ten evaluator tests pass (one optional Docker skip), including lost-quote and changed-project rejection. Local branch only; no new provider trial or runtime rollout.

- 2026-10-11 | Private bound understanding collector implemented locally: fixed 36-trial plan, explicit models, owner-only prompts/responses/report, input/binding change refusal and preserved failures. Twelve evaluator tests pass (one optional Docker skip). Live Codex run terminal: two transport failures, 34 blocked trials, zero scored; no model improvement measured.

- 2026-10-11 | Added private per-trial raw transport retention and owner-only permissions; 12 evaluator tests pass (one optional Docker skip). Live diagnostic gpt-5.5 succeeded; requested identity recorded, reported model remains unknown.

- 2026-10-11 | Live study interim: 16/36 trials scored, 15 whole-response passes. Arabic latest-correction failed in raw history and passed in paired selected context. Existing live collection session 77308 and full-gate session 13616 remain active; no final improvement claim.

- 2026-10-11 | Full repository gate passes for private understanding collector and input audit: public structure, Python syntax, links and requested regressions; explicit runtime-dependent skips remain. Paired collection still running separately.

- 2026-10-11 | Actual private paired study complete: 36/36 scored, frozen inputs unchanged. Raw history 14/18 versus selected context 17/18 (EN 7/9 vs 8/9; AR 7/9 vs 9/9). Requested gpt-5.5, reported identity unknown. Zero scope-ID/publication-intent/verified-claim errors. Nine synthetic cases, one trial per condition; no statistical or general-delivery claim. PR #16 opened from gated commit 06401c9.

- 2026-10-11 | Actual first ledgerline run preserved: billing verified, planning generation failed container acceptance, report correctly blocked; worker overlap confirmed. Reused helper source now declared in billing/planning/report generation inputs; 38 example tests pass (3 runtime-dependent skips). Independent closure-corrected project created for a separate real attempt.

- 2026-10-11 | Contract alignment: invalid-input grader now checks required ValueError without undocumented wording; public cycle contract explicitly repeats start ID at end. Alternate valid error wording accepted, RuntimeError rejected. Full Docker example suite passes 39 tests. Separate bound agency-ledgerline-contract-20261011 actual coordinator attempt started, prior three failures retained.

- 2026-10-11 | Live contract-aligned coordinator interim: billing and planning verified by actual container acceptance; report running after merged ancestors, worker overlap confirmed. Full combined delivery remains pending; previous three attempts preserved.

- 2026-10-11 | Report contract exposes exact bilingual title resources. Report refusal grading accepts legitimate wording but requires unknown-field naming; regression accepts alternate messages and rejects missing field name. Full Docker example suite passes 40 tests. Separate actual report-fix batch started; previous failures preserved.

- 2026-10-11 | Combined unknown-field check now requires actual offending key extra rather than hidden phrase. Alternate error wording accepted; missing key name rejected. Full Docker example suite passes 41 tests. Actual generated integration bytes separately reverified with corrected grader in network-free read-only container: combined 13/13 and helpers 16/16. Original failed prepare unchanged; coordinator publication not yet approved.

- 2026-10-11 | Initial evidence-driven repair runtime added in existing workflow runner. Twenty-nine workflow cases pass locally (five optional Docker cases skipped in that run); regression rejects altered candidate, changed original input, foreign checkout and substituted verifier. Full Docker workflow run pending; no live repair-quality claim.

- 2026-10-11 | Evidence-driven repair workflow Docker suite passed all 29 cases; producer-before-verifier guard added and final Docker rerun initiated under exec66482. Actual provider repair payload/chain acceptance and publication still pending.

- 2026-10-11 | Added one-command private repair preparation/execution, full-prompt budget and verifier-image checks. Workflow 31 cases passed in Docker; privacy 19 cases passed including real forced private commit rejection and clean commit acceptance. Separate bound live Codex pilot (requested gpt-5.5, reported identity unavailable) repaired an intentionally seeded broken Unicode slug; actual isolated bilingual acceptance passed 5/5 and original failed journal stayed byte-identical. This is transport/repair evidence, not a weak-model or Claude comparison.

- 2026-10-11 | Final repair budget guard counts all model repair requests by original workflow across new IDs and branches. Regression rejects a branch after two requests, an oversized feedback prompt before provider calls and a substituted verifier image. Final Docker workflow31 passes.

- 2026-10-11 | PR #16 review fixes: freeze actual evaluate_hosts grader and audit exact ordered records per arm rather than subsets. Fourteen evaluator tests pass (one optional Docker skip), including grader mutation invalidation and obsolete-selected/missing-raw rejection. Original live pilot predates grader fingerprint and is supporting evidence only.

- 2026-10-11 | Local OpenCode profile support and English guide added. Model-host33 cases pass with actual OpenCode1.18.32 loopback protocol fixture enabled; workflow32 Docker cases pass, including changed-profile publication/reuse refusal. Separate real opencode/space-bunny-free feature attempt failed transport before producing code; retained privately and not scored as model quality. No actual local inference benchmark or universal improvement claim.

- 2026-10-11 | Mandatory merged-source hook passed public structure, syntax, links and all requested regressions. Memory history repaired and revalidated before final PR readiness; final documentation-only commit gate pending.

- 2026-10-11 | PR17 final initial head passed all nine CI checks. Review P2 reproduced acceptance of mode0644 provider files; loader now refuses it and accepts mode0600. Actual OpenCode model-host33 and Docker workflow32 regressions pass after the ownership fix; mandatory review-fix commit gate pending.

- 2026-10-12 | Added host-neutral agent-packet CLI and English host guide. Workflow34 tests pass with all Docker cases enabled: packet preserves journal/output state, makes no provider call, carries Arabic and identity/schema/hash data, refuses in-flight source changes, cancelled tasks and stale enforced context. PR17 merged at 2b8508b; installed exact snapshot and validate passed42 skills. New packet publication/runtime update pending.

- 2026-10-12 | PR18 late-input mutation review fixed; workflow34 passes all Docker cases again. The new regression verifies a change after the final prompt read is refused; final hook and exact-head CI pending.

- 2026-10-12 | Ported intended other-agent browser source onto current main without modifying dirty original. Dashboard46 tests and production build pass. Actual headed Chromium29 cases pass with one optional screenshot skip: real capture/click/index, disabled actions and persisted state; negative DOM spoof/removal/hidden/stale cases pass. Actual dashboard HTTP refuses foreign Origin before OS probe; English/Arabic/mobile UI tested with unknown connection and no overflow. Codex CLI installed/enabled crewloom@crewloom-local0.1.0; cached manifest/skill/icon verified. No autonomous model/browser bridge claim.

- 2026-10-12 | Installed native Codex plugin and real browser/dashboard checks remain verified; packaging18 cases now pass after public asset contract expansion. Full corrected commit gate pending.

- 2026-10-12 | Initial integrated commit c009813 passed the complete mandatory hook. Final native Chrome test now additionally confirms generation-less click requests are refused; all29 browser checks pass again with one optional screenshot skip. Final fix commit gate pending.

- 2026-10-13 | PR19 review fixes implemented. Dashboard47 tests pass; headed Chrome30 tests pass with one optional screenshot skip, including non-export of entered form values. Added rendered first-open/changed-tab regression; final gate/publication pending.

### 2026-10-14 — Browser/dashboard defect closure
- Artifact: existing browser/dashboard modules, source packager and documentation/BROWSER_DASHBOARD_ACCEPTANCE.md.
- Evidence: original tab/DOM/metrics regressions reject old behavior; Python1123 (1016pass/107skip), dashboard55, TypeScript/build, Docker workflow34/policy43, actual Chromium38pass/1optional skip, distribution12 pass. ZIP rejects stale/unreviewed content and accepts deterministic rebuilds. Local rollout follows the gated commit; autonomous MCP/desktop integration is a separate phase.

### 2026-10-14 — MCP and reply import acceptance
- Artifact: scripts/mcp_bridge.py, workflow import-reply, documentation/MCP_BRIDGE.md and scoped client templates.
- Evidence:10 bridge/import tests pass with real stdio and Docker; all five Crewloom tools called, plus actual Playwright navigate/snapshot/click/close against an isolated synthetic fixture. Both configs validate; distribution13 and packaging20 pass, Docker publication43 pass. Native Codex registration/runtime rollout follows the gated commit; no paid generation, desktop or broad model-quality claim.

### 2026-10-14 — Verified local runtime rollout
- Artifact: immutable Git snapshot bb6c68fb5c0bac5ed69500316edd6cb990015064 installed through pipx with the MCP extra; dashboard serves the same snapshot and preserves its monitored project. Prior snapshot retained.
- Evidence: actual CLI source and SDK2.3.0 confirmed; HTTP overview/page/extension ZIP200, foreign-origin ZIP403, exact ZIP2.3.0 checksum matches source. Rendered English1440px/Arabic390px pass without horizontal overflow or page errors. Codex read-only config registered; its exact installed launch command lists/calls crewloom_status and crewloom_context successfully. Current chats require a new host connection to load tools.

### 2026-10-14 — Typed run-history follow-up
- Artifact: dashboard/lib/repo.ts and dashboard/test/repo.test.ts.
- Evidence: regression rejects the prior parser (10 rows accepted instead of2);56 dashboard tests and TypeScript now pass. Required timestamp/role/duration/source fields and optional output/root are validated before history can reach metrics or React. All547 existing local rows have the required fields. Operational installation evidence remains project-private.

### 2026-10-14 — Capture and bounded capability continuation
- Artifact: existing user-context/native lifecycle/MCP modules; scripts/native_desktop.py, synthetic Swift target and documentation/NATIVE_DESKTOP.md.
- Evidence: capture8 incl real SDK answer protocol; lifecycle75 (2optional skips), OpenCode36, packaging20, native mock4 pass; Swift fixture compiles. Two requested CLI models each yield selected-context4/4 versus raw-history2/4 on two bilingual scenarios; actual backend model identity unreported. Configured model rejection preserved. Full commit gate/local installation pending; human manifest approval/live Accessibility proof pending.

- 2026-10-14 | Continuation commit ef7782a passed the mandatory99-suite/1207-test repository gate (optional live suites retain their skips). Immutable source installed with pinned MCP extra; exact installed stdio command lists/calls all three read tools. No native driver launch or automatic host capture activation; approval remains pending.

- 2026-10-15 | Artifact: native_desktop.py, opt-in live regression and native guide. Real approved CuaDriver/SDK acceptance passed: counter0→1→0, stale/unobserved handles and foreign PID refused. Seven offline tests pass; live suite skips unless explicitly enabled. Expired session and denied global-discovery attempts retained privately; installed rollout follows the mandatory gate.

- 2026-10-15 | Corrected immutable release ae387fe passed the mandatory99-suite/1211-test gate (optional skips). Exact installed Crewloom native CLI passed real counter0→1→0 and stale/unobserved/foreign-process refusal. Approved daemon stopped and owned fixture closed; receipts remain project-private.

- 2026-10-15 | Artifact: coordinator/user_context delivery guard, native exact target/read-only preparation, import-contract clarification. User-context18 and native10 tests pass (native live case remains opt-in); real Docker coordinator49 passed. Public PR20 opened for the prior gated fixes. Paired model delivery and broader live application acceptance continue with preserved failures.

- 2026-10-16 | Operational acceptance delivered: four real generated modules,70 application cases +16 helper tests, exact credential-reviewed local publication, unchanged verified generation counts on resume, and executor-verified Arabic correction. Actual Chrome profile2.3.0 index/click/capture, Calculator exact12 and TextEdit read-only pass; test sessions stopped.42 guides validate; live role coverage is explicit. Distribution13 passes for0.6.0; final release gate/merge/install follows.

- 2026-10-16 | Browser PR20 review closure: tracked cleanup includes all contacted frames and partial failures; remaining index quota is reused; unverifiable cross-origin targets are omitted with a warning. Four new checks reject37f8387; final real-browser42 passes (one optional skip). Chrome profile upgrade2.3.1 verified index/click/capture/clear, then disabled and owned server/tab closed.

- 2026-10-17 | Browser companion2.3.2 localizes known error details, HUD statuses, empty capture, toggle labels and accessible control names. Paired direction/reload/frame cases and known-bad release rejection are exercised; full release gate and operational rollout follow.

- 2026-10-17 | Paired rendered browser46 passes (one optional screenshot skip); three new regressions reject the previous released source. Evaluator14 and context19 pass. Actual profile2.3.2 verifies Arabic HUD on English site, English HUD on Arabic site, exact click effects, saved Arabic after reopen and hidden-state preservation; companion disabled and owned tab/server closed.

- 2026-10-17 | Capture-disable race translation and internal-error coverage check added after review. Initial corrected real-browser47 passes (one optional skip), and the additional internal-error check passes. Final combined48-case suite, normal gate and exact-head CI follow.
