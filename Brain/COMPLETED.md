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
