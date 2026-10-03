# Challenges

### 2026-10-01 — Separate public tooling from private operations
- Cause: The upstream workspace mixes reusable roles with client data and agency-specific contracts.
- Solution: Publish English public adaptations, clean memory, and selected inspected tools in a new repository without upstream Git history.
- State: Initial edition isolated; specialist workflows still require host tools and user-specific setup.

### 2026-10-01 — Over-compressed public procedures
- Cause: Initial adaptation reduced specialist procedures to brief role outlines.
- Fix: Restore filtered detailed references and publish an explicit executable tool catalog.
- Check: Review content depth and run published examples before releasing.

### 2026-10-01 — grid-safety false positives behind breakpoint prefixes
- السبب الجذري / Root cause: the check flags any `minmax(Npx,...)` floor without modeling that `lg:` only applies at >=1024px.
- الحل المعتمد / Approved fix: breakpoint-aware guard in `check_responsive_grid_safety.py`; evidence in `documentation/EVIDENCE.md`, task queued in ROADMAP_TODO.
- الحالة: محلول (2026-10-01) — prefixed floors (sm..2xl) are skipped when their sum is at most half the breakpoint; 4 regression tests

### 2026-10-01 — Evaluation fixture too easy to discriminate
- السبب الجذري / Root cause: seeded defects are standard patterns a strong generic reviewer already catches.
- الحل المعتمد / Approved fix: harder fixtures, repeated runs, blind grading (queued in ROADMAP_TODO).
- الحالة: مفتوح

### 2026-10-01 — Project path isolation
- Cause: Library and project roots were conflated for execution, memory, and logs.
- Fix: Separate canonical roots and validate resolved input/output/install paths.
- Check: Two-project fixtures exercise identical filenames and symlink escapes.

### 2026-10-01 — Role installation memory isolation
- Cause: Force installation removed the whole role directory, including project memory.
- Fix: Refresh reusable files, preserve existing brain, initialize clean local records on first install.
- Check: Seed private history and verify it survives update; reject redirected destination files.

### 2026-10-01 — Executable software workflows
- Cause: Role procedures alone did not execute work, isolate subprocesses or prevent stale evidence.
- Fix: Docker-only commands, project-bound state, fingerprints, attempt limits, locks and task handoffs.
- Check: Live container tests plus objective acceptance; task review identity and host sandboxing remain external.

### 2026-10-01 — Model host diagnostics and unavailable authentication
- Cause: Codex nonfatal diagnostic items were mistaken for executable tool events; Claude CLI is installed but logged out.
- Fix: Require completed structured generation, count diagnostics separately, reject executable/unknown tool items; preserve provider failures and skip calls after two host failures.
- Check: Diagnostic regression and actual Codex/Docker feature pass; Claude comparison remains blocked until local login.

### 2026-10-02 — Instructions cannot constrain arbitrary host tools
- Cause: writable project mounts and native CLI processes exceeded the intended artifact boundary.
- Fix: declared-input snapshots, individual output mounts, trusted publication and tool-free API generation; native CLI requires operator opt-in.
- Check: actual Docker rejects input/runtime/undeclared writes and accepts a declared output. Arbitrary host agents remain outside this boundary.

### 2026-10-02 — Context efficiency
- Cause: growing completion/challenge/idea histories were resent in full, and completed model reuse did not check changed guidance. Fix: whole-record selection with omission counts and prompt-hash validation. Check: retained relevant old lesson, preserved rules, changed-context rejection and unchanged reuse acceptance.

### 2026-10-02 — Repository navigation
- Cause: full source context is expensive and stale navigation can misdirect edits. Fix: bounded symbol index with content-hash refresh, deletion pruning and explicit root checks. Check: changed/added/deleted files refresh; redirected/foreign cache rejected.

### 2026-10-02 — Automatic context implementation plan
- Planning finding: local map caches do not supply automatic lifecycle, portable identity or verified learning; JS/TS extraction/import resolution and oversized seed omission need correctness gates before unattended use. Proposed response: explicit identity, versioned snapshots, staged adapters and evidence-linked lessons.

### 2026-10-02 — Implemented project context and the gaps it closed
- Cause: three implementation defects were reproduced during implementation, not only planned. A task snapshot silently dropped a declared source body and exceeded its own byte budget; a lesson could be "verified" from a self-asserted exit code; finalization reported completion without any executed check.
- Fix: required content now fails the task instead of disappearing and the serialized payload is measured; lesson promotion resolves recorded executor evidence from workflow state and the attempt ledger; finalization reports complete, awaiting_verification or failed from real exit codes.
- Check: forged-success, missing-check, failing-check, stale-range and dropped-body cases are rejected regressions, while a real executor run promotes a lesson with scope and fingerprints.
- Cause: the agency project-control ledger is agency-private, so a first adapter invented an incompatible absolute-path schema and status set.
- Fix: the adapter validates the authoritative contract (schema 1, `projects`, `id`/`active_dir`/`context_snapshot`/`delivery_owner`/`control_status`/`last_verified_at`/`next_action`/optional `state_evidence`, agency-root-relative paths, five control statuses) and can run an explicitly selected agency validator first.
- Check: temporary agency-root fixtures cover valid entries, needs_reconciliation, blocked, changed evidence, absolute paths, escapes, unknown roles and unknown statuses.
- Remaining: live provider token/cost effects, real client pilots, host callbacks and richer JS/TS resolution stay deferred until measured.

### 2026-10-02 — Independent review exposes missed boundaries
- Cause: Reentrant ownership survived a fork, rejected tasks wrote context, identical-content paths shared keys and generation metadata caused repeated refreshes. A corrected evidence predicate also rejected genuine successful commands.
- Response: Independent rejected-violation tests plus real executor positives; retain original scope and attempts during compact exact-model delegation.
- Resolution: ownership is keyed by process, thread and canonical folder so a forked child contends; entry preflights ownership before any metadata write; range cache keys include the relative path; the semantic fingerprint excludes the generation counter, recorded size and telemetry; evidence promotion separates the recorded executor outcome from later artifact drift.

### 2026-10-02 — Optional evidence outgrew the task budget
- Cause: range hints multiplied by twelve symbols per file, and the full indexed-file name list was stored, so a 2001-file scoped project produced a 521,691-byte generation against a 131,072-byte budget and entry failed outright.
- Response: required content (governing rules, criteria, declared bodies, seed navigation) is sealed first, then optional ranges, test hints and neighbour hints take only the exact remaining serialized room; the indexed inventory is recorded as a digest plus a bounded sample; scan caps are enforced where the index enforces them.
- Check: dense 110-dependency fan-out and a 2002-indexed-file scoped reproduction both stay inside budget with the declared body and seed intact and an explicit `ranges` omission recorded.
- Cause: freshness compared every source path against a name list built with the wrong policy.
- Response: `repo_map.inventory` reproduces the index's own scope, exclusions, size caps, decodability and scan caps, so out-of-scope or skipped files never invalidate while in-scope create/delete/rename always does.
- Check: scoped inventory, non-UTF-8 source and beyond-cap new file are covered by rejected/accepted regressions.

### 2026-10-02 — Delivering a frozen snapshot is not the same as delivering it
- Cause: the managed prompt builder never consumed the frozen generation, so a model could silently lose required context even though the snapshot was stored and gated.
- Response: the prompt carries the frozen scope, generation, semantic SHA, complete governing rules, verified remedies, bounded ranges and recorded omissions, and a resumed step is re-bound to the immutable archived generation it originally consumed.
- Check: the managed prompt regression asserts the project and checkout identity, the verified remedy and the immutable semantic SHA reach the actual adapter call.

### 2026-10-02 — Synthetic acceptance silently stopped running
- Cause: the pilot declared one input while its acceptance command discovered a test package, so the isolated executor failed, and the pilot reported a fixed exit code instead of the real one. Python 3.14 unittest also stopped collecting module-level test functions.
- Response: the acceptance plan declares every file the check reads plus the artifact it writes, the fixture uses `TestCase` classes valid from 3.9 to 3.14, and missing declarations report `executed=false` with a reason instead of a claim.
- Check: both synthetic sizes execute acceptance inside Docker and finalize through correlated executor evidence; without a reachable Docker daemon the acceptance tests skip instead of failing or passing silently.

### 2026-10-02 — Optional ranges filled the global context ceiling
- Cause: suggested ranges were admitted from whatever room the required bodies left, and the file cap multiplied by twelve symbols per file, so one dense project spent 85 KiB of a 131,020-byte generation on unrelated symbol records and the acceptance workflow could no longer read the snapshot back with its rules and declared sources.
- Response: ranges take their own allowance (`budgets.range_bytes`, defaulting to `map_bytes`) and at most 64 records across all files, seed ranges first; the omission records the real dropped count.
- Check: local dense reproduction keeps 23 records / 7928 bytes inside an 8192-byte allowance and its snapshot plus rules plus declared sources fits 131,072; the same fixture without the allowance is refused at 131,137 bytes. The authorized real project rerun is the supervisor's evidence, not this fixture.

### 2026-10-02 - Scan and body budgets were checked after the bytes were read
- Cause: the freshness inventory counted only bytes that decoded, so decoder-rejected candidates evaded the aggregate cap, and a declared body larger than the context budget was read into memory before being refused.
- Response: every candidate byte counts against the aggregate budget before the decode attempt, and an oversized required body is refused from its declared size.
- Check: rejected regressions prove the extra source is rejected before its `read_bytes`, while unchanged skipped files still keep a generation fresh.

### 2026-10-02 - Reuse guessed which archived context a step consumed
- Cause: the reuse check matched a generation by declared source paths and role, so two model steps with identical inputs could resolve each other's generation, and a newer context invalidated both.
- Response: each model step record binds the generation and semantic SHA it consumed, and reuse resolves that exact immutable archive; a record without the binding cannot be reused.
- Check: two same-input model steps each reuse their own consumed generation and produce no second provider request.

### 2026-10-02 - First native entry invalidated its own frozen instructions
- Cause: entry froze the context and then wrote the managed block into the authorized instruction file, and the generated exit line ended in a literal backslash-n that swallowed the following text.
- Response: the bounded managed block is written before the freeze, after the ownership check, and each command is one runnable shell line with shell-quoted JSON evidence.
- Check: first opted-in entry is immediately fresh, the customer constitution survives, and an unchanged repeat reuses the same generation; the exit line is shlex-parsed and JSON-decoded by an independent regression.

### 2026-10-02 - Stored evidence was trusted where the runtime had not checked it
- Cause: entry delivered a frozen snapshot without the navigation index, a managed map request scanned the whole tree instead of the bound scope, a lesson selector trusted a record count instead of serialized bytes, entry never revalidated verified lessons, and a managed run that failed during entry left the root reserved with no way to cancel.
- Response: the prompt carries the frozen navigation, managed maps use the bound configuration, lessons are measured as the exact stored JSON array, entry revalidates verified lessons, and a reserved but unstarted run is explicitly cancellable.
- Check: five independent regressions cover prompt navigation, bound source roots, the lesson byte budget, automatic lesson invalidation and cancelling a failed entry.

### 2026-10-03 - A repeat measurement cannot differ only by the project root path
- Cause: the pilot's repeat test asserted that the serialized size of two identical measurements differs only by the length of the canonical root, but the generation also records the measured scan duration. `repo_map.build` rounds `duration_ms`, so its digit count changed the exact sealed payload size; the premise was false and the test flaked rather than the product misbehaving.
- Response: keep every recorded byte actual and compare generations through a deterministic normalization that blanks only named paths: the derived `bytes`/digests, `created_at`, `telemetry.generated_at`/`duration_ms`, `scope.project_root`, `scope.checkout_id`, `map.checkout_id` and the checkout-scoped `ranges[].cache_key`. Report `stable_sha256`, `stable_semantic_sha256` and the exact `volatile_bytes` count so a size difference is explained, never padded.
- Failed attempt kept as history: 1) normalizing by key name anywhere in the tree still left identity material in `ranges[].cache_key` and `map.checkout_id`, which the strict digest caught; 2) blanking identity and timing but leaving the derived top-level `bytes` numeric value made a resealed payload still differ, because sealing recomputes that total from the timing digits. Both were replaced by the path-based normalization above rather than retried unchanged.
- Check: forced timings 9 and 1234567 resealed through `project_context.seal` give exact 6665/6671 recorded bytes, equal stable payload and semantic digests, and a volatile byte delta equal to the timing digits alone; a changed body text and a moved range start are still rejected, so normalization cannot hide real content drift.

### 2026-10-03 - Commit-hook Git environment bound project work to the committing repository
- Cause: `repo_map` and the repository fixtures started Git with only a working directory, so `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, the object-store variables and the `GIT_CONFIG_*` block were inherited. The pre-commit hook exports those for the repository being committed, so the commit gate discovered the outer checkout instead of the temporary project it was given: fixture `init/add/commit/checkout/branch` rewrote the outer HEAD, index and configuration, created a `first` commit and a `feature` branch there, and an unborn fixture repository reported the outer commit as its head. An explicit `cwd` is not isolation when the location comes from the environment.
- Response: every Git child starts from `repo_map.git_environment()`, which drops each `GIT_` variable except `GIT_AUTHOR_*`/`GIT_COMMITTER_*` and keeps `PATH`, locale and time zone, and `require_git_root` additionally requires the discovered repository to be the one the root's own `.git` marker names with its work tree at that root. Bare repositories, subdirectories of another checkout and plain directories are refused. The runtime test fixtures and the synthetic pilot use the same cleared environment.
- Failed attempt kept as history: clearing the environment alone was not enough, because `git rev-parse --git-dir` still succeeds for a subdirectory of another checkout, so the root could silently index a relative path set against a foreign work tree; the `.git`-marker and work-tree equality check is what makes the binding exact, and it is what keeps a linked worktree (this checkout is one) mapped as its own root.
- Check: the whole suite under a faithful hook environment pointed at a throwaway repository reports 30 failures and 8 errors with a leaked `first` commit and `feature` branch before the fix, and 0 failures / 0 errors afterwards with the foreign HEAD, index, configuration, refs and history byte-identical and its pending work still untracked. Regressions map the selected repository from an environment exported by the other one in both directions, refuse a plain directory, a nested directory and a bare repository without initializing anything, map a linked worktree as its own root, and reject any fixture that starts Git without an explicit environment.

### 2026-10-01 — Paused tasks released process ownership
- Cause: Process locks ended on manual-task handoff, permitting a different workflow to start in that root; implicit cwd also allowed ambiguous selection.
- Fix: Require explicit task root and persist a project-bound active-workflow reservation; only matching continuation/cancellation may take over.
- Check: Concurrent same/different-root, paused-task, cancellation and redirected reservation regressions. Direct host edits remain outside runner protection.

### 2026-10-03 - The hosted validate job ran live acceptance without providing its pinned image
- Cause: `context_pilot.docker_available` gates the live pilot suite on a reachable Docker daemon only (`docker info`), which hosted `ubuntu-latest` satisfies. The pinned `workflow.DEFAULT_IMAGE` was then absent from the fresh runner, so `workflow.inspect_image` correctly refused to execute and the acceptance ran as `executed=false`/`verified=false`, failing `acceptance_executed` and `finalization_verified` with CLI exit 2. `check_repository.py` discovers `scripts/test_*.py`, so the `validate` matrix inherited these live cases; only `isolated-workflows` pulled the image first. Local and archive runs passed because the local daemon already held it.
- Response: the `validate` job now runs `docker pull python:3.14-slim` before the unchanged `check_repository.py` gate, mirroring the existing isolation job, so both matrix interpreters supply the prerequisite. The executor still refuses an absent pinned image; nothing was skipped, weakened or made to pull implicitly.
- Check: `python3 -m unittest discover -s scripts -p test_context_pilot.py` passes all 7 cases including the 3 live ones that hosted CI failed on, and `python3 scripts/check_repository.py` reports 310 cases, 6 skips (the unchanged `CREWLOOM_DOCKER_TESTS` opt-in policy class) and exit 0.

### 2026-10-03 — Final evidence reconciliation
- Cause: Earlier draft counts and interpreter coverage predated the hook-environment fix and main integration.
- Solution: Preserve historical entries, label scripts versus total cases, and use actual post-integration 310-case gate, 250 live Docker cases and 30 independent boundaries in final evidence.
- Evidence: Python 3.9 container and extracted source archive both terminate with exit 0; manifest detections reviewed as fixture file hashes.
