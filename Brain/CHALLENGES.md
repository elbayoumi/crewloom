# Challenges

### 2026-10-15 — Python 3.9 native lock construction
- Cause: asyncio.Lock was created by a synchronous controller constructor; Python 3.9 eagerly binds it to an absent/old loop after asyncio.run, causing six hosted errors.
- Solution: lazy allocation inside the running operation loop, explicit foreign-loop refusal and contended serialization regression; nine offline cases pass on actual Python 3.9 and 3.14, one approved-live case remains opt-in.
- Status: Resolved locally; rerun exact-head hosted matrix before merge.

### 2026-10-15 — Explicit acceptance skipped prerequisites
- Cause: browser launch/build backend failures raised SkipTest during explicit acceptance; hosted CI omitted real MCP/browser protocols.
- Solution: fail explicit prerequisite errors, clean browser setup, add actual SDK/headed-extension CI. Bad/clean regressions and live acceptance pass.
- Status: Resolved locally; hosted evidence belongs to the proposed commit.

### 2026-10-15 — Setup and dependency contracts drifted
- Cause: first launch used npm install despite a reviewed lockfile; Arabic/release login and health prose predated implementation changes.
- Solution: npm ci with failure-stop regression, Node/ES module metadata, source-install commands for unpublished extras and current bilingual setup/release checklist.
- Status: Resolved locally; dashboard56, TypeScript/build and package acceptance pass.

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

### 2026-10-03 — A published secret is no longer a secret once a command prints it
- Cause: `crewloom dashboard` minted a dashboard token and printed it with a "shown once" banner, and `crewloom reviewer register` printed the issued credential as JSON. Standard output is a log: it reaches terminal scrollback, CI job output, shell tracing and any process that captures the command, so a generated secret that is printed cannot be treated as operator-only. Neither the browser bundle nor a query string was involved; the leak was in the delivery.
- Response: the dashboard token is written to `<project>/.crewloom/dashboard-token` and an issued reviewer credential to `.crewloom/reviewer-token-<principal>`, both mode `0600` through an owner-only temporary file and an atomic replace, and only the path is printed. `reviewer register --show-token` remains an explicit opt-in for an operator who deliberately wants it on standard output.
- Check: an installed-wheel distribution case asserts `crewloom dashboard` prints no token at all, and the reviewer case asserts the registry stores only the hash, the issued file is `0600`, and the JSON output carries no `token` field by default.
- Second finding kept as history: writing through a predictable `dashboard-token.tmp` name let a pre-planted symlink redirect a secret write into another project, because `open(..., 'w')` follows the link it finds. The temporary file is now created with `tempfile.mkstemp` under a random name with `O_EXCL`, and the ownership check rejects a symlinked destination.

### 2026-10-03 — A source-archive link gate measures packaging, not writing
- Cause: the sdist pruned `.github` and `.githooks` and shipped only `assets/*.svg`, while `README.md` linked to `assets/dashboard-demo.gif`, `assets/dashboard-demo.mp4`, `Brain/`, and `.github/workflows`, `documentation/EVIDENCE.md` linked to `../Brain/COMPLETED.md`, and a role playbook linked to the root `MASTER_BRAIN.md`. Running the public structure checker against the extracted archive reported six broken links while the same checker passed on the checkout, so the failure looked like broken documentation and was actually missing packaging.
- Response: the manifest includes `MASTER_BRAIN.md`, `Brain/`, `.github/`, `.githooks/` and the referenced demo media, and prunes only private runtime state, generated output and dependencies. Broken links stay a real signal, so nothing was deleted from `README.md` to make the gate pass.
- Check: rebuilding the sdist with the isolated build frontend and running `check_repository.py --skip-tests` on the extracted tree now exits 0; the archive carries no `.crewloom`, `node_modules`, build or log entries.

### 2026-10-03 — An issuance authority at the project root was a declared input
- Cause: the reviewer registry was `crewloom.reviewers.json` in the project root. It held the token hashes and per-credential epochs that every stored approval is signed with, which made it a trackable project file: a step could declare it as a workflow input, it could be copied into a task context body, and it could be committed or indexed.
- Response: the registry moved to `.crewloom/reviewers.json`, resolved with `safe_path(..., internal=True)`, so the existing runtime-state rule already refuses it as a declared artifact or context body. Loading additionally refuses a symlink, a hardlinked or non-regular file, and on POSIX any file not owned by the current user or readable by group or other.
- Failed attempt kept as history: renaming the file alone was not enough. It was paired with the ownership and mode refusal, because a registry the group can read is not the issuance authority the signature claim depends on. A platform without POSIX permission bits cannot be checked this way, and `reviewer status` says so instead of implying a guarantee.
- Check: the independent credential acceptance suite passes 10/10, including that the registry cannot be declared as a workflow input, cannot be a broker output, cannot appear in a declared context body, and that a world-readable registry stops authorizing an otherwise valid approval.

### 2026-10-03 — Lock reclamation deleted files it had never created
- Cause: the root lock's stale-owner reclamation cleaned up its own exclusive `.reclaim` directory with `claim.rglob('*')` and unlinked every child it found. `rglob` follows a symlinked directory, and `claim.mkdir()` on a `.reclaim` symlink raises `FileExistsError`, so the code walked straight into whatever the link pointed at. The independent third lock case pointed `.reclaim` at an unrelated directory holding a dead-PID `owner.json` plus `keep.txt`, and the first two cases already passed, so the flaw was invisible to the earlier checks. `_release_reclamation` had the same recursive walk, and `_restore` separately unlinked a predictable `.crewloom-publish-<transaction>-<index>` name that `_apply` never created, so it could delete a foreign file that happened to match.
- Response: a claim is used only when `_owned_claim` proves it is a real directory this protocol created, containing only `owner.json` and `pin` as regular non-symlink files; anything else returns `None` and blocks the root for manual reconciliation. `_discard_claim` unlinks those two exact names and then relies on `rmdir`, which only succeeds on an empty directory, so no tree outside the claim is reachable. A symlinked lock file is never read, pinned or unlinked. `_apply` no longer computes the predictable temporary name and `_restore` no longer deletes it; the real staged file is an anonymous `NamedTemporaryFile` whose residue is left for an operator rather than removed by guesswork.
- Failed attempt kept as history: the first B3 note claimed the six grouped-publication cases were failing and that publication still replaced destinations one at a time. Re-running them first showed 6/6 already passing, because an earlier interrupted run had landed the transaction implementation. The note was corrected rather than acted on, and the real remaining work was the lock finding plus the contract gaps below. Acting on the stale claim would have meant rewriting working publication code.
- Check: the independent lock suite passes 3/3, where the third case previously raised `FileNotFoundError` on the foreign `keep.txt`, and the foreign directory keeps both `keep.txt` and `owner.json` intact.

### 2026-10-03 — A rollback that validated records one destination at a time
- Cause: `_rollback` iterated destinations in reverse and let each `_restore` raise on its own ambiguous destination, so a group whose last destination had been edited by a third party could already have restored the earlier ones. That produced a third state nobody recorded: partly reverted, with no journal describing it. Separately, a failed in-process publication left its journal in `pending/`, so every failure accumulated residue that the next publication had to reconcile before doing anything, and `_discard` deleted whatever `rglob` found inside a transaction folder.
- Response: `_validated` proves every record restorable before any rollback byte is written, so either the whole group is reverted or none of it is. A fully reverted group is finished, so `_abandon` writes a bounded `rolled-back` receipt and releases the journal instead of leaving residue. `_discard` recognises exactly `journal.json`, `backup` and `payload` and deletes them by name, reporting anything else as manual reconciliation rather than deleting it. `_pending` refuses a symlinked transaction instead of silently skipping it and leaving a half-published group unreconciled. A rollback that cannot finish is raised with the original write failure as its `__cause__`, so the caller's own error survives and the refusal is not hidden.
- Check: the independent grouped-publication suite passes 6/6; own cases confirm that an ambiguous second record leaves the restorable first destination still applied and the journal preserved, that an unrecognised staged file is reported and left, that a failed group leaves no pending journal but a `rolled-back` receipt, and that the root lock file is present for every destination of a successful group.

### 2026-10-03 — `js_syntax` was imported by the navigation index but not packaged
- Cause: `repo_map` imports `js_syntax` at module scope, but `pyproject.toml` declared neither `js_syntax` in `py-modules` nor any optional dependency, so an installed wheel would have failed at import and the verified grammars had no declared place. The module is standard-library-only at import time and loads the grammars lazily, so the fix was a declaration, not a refactor.
- Response: `js_syntax` joins the flat `py-modules`, and one optional extra `crewloom[syntax]` pins `tree-sitter==0.23.2`, `tree-sitter-javascript==0.23.1` and `tree-sitter-typescript==0.23.2`, which are the exact versions the pinned verification environment resolved. Core `dependencies` stays empty. New packaging regressions check that every declared flat module has a source, that the module `repo_map` needs is declared, and that the extra pins the verified versions.
- Check: `python3 -m build` produces a wheel and sdist that both carry `js_syntax.py`, 42 role `SKILL.md` files and zero `.crewloom` entries; metadata declares `Provides-Extra: syntax` and the three exact pins; the opt-in distribution suite passes 11/11 with `--no-deps` installs, proving every command still works without the extra.

### 2026-10-04 — A worktree records no project identity until something bootstraps it
- Cause: a linked worktree starts with no `.crewloom` at all, so `workflow.state_for` recorded `project_id: null` and `checkout_id: null` the first time a batch ran a task there. The coordinator's own check "the managed run must belong to this portable project and to a different local checkout" then refused every task, even though the workflow had executed correctly. The single-workflow path never saw this because a project is bound before its first run; only the coordinator creates roots that are unbound by construction.
- Response: each worktree is bootstrapped with `project_binding.bootstrap` under its own project lock before its plan is read, which is idempotent and yields the same portable project identity with a new local checkout binding. The refusal that exposed the gap became the invariant: a worktree that reuses the root's checkout binding is still refused.
- Failed attempt kept as history: reading the workflow evidence after the run and trusting `binding_id` to have been populated was the first approach; it reports `None` rather than failing, so the evidence looked complete and the check fired on a real success. Reading the identity before the run was not the fix either — that is the same bootstrap, only placed earlier.
- Check: the real three-task batch records three distinct `checkout_id` values under one `project_id`, and a regression refuses a worktree that reuses the root binding.

### 2026-10-04 — A read-only preflight rewrote the Git index
- Cause: the coordinator's clean-base check compared the work tree with `git diff --name-status`. Git refreshes `.git/index` opportunistically to cache stat data, so a command that only inspects the repository rewrote the index file. The independent read-only acceptance case made this visible: with one tracked file's mtime changed but its content identical, `validate` returned `validated` and the index bytes had moved. `GIT_OPTIONAL_LOCKS=0` did not help, because `git diff` refreshes regardless.
- Response: every Git child of the coordinator runs under `repo_map.git_environment()` plus `GIT_OPTIONAL_LOCKS=0`, and the clean check uses `git status --porcelain=v1 -z --untracked-files=no`, which performs the same staged and work-tree comparison under that setting without writing the index.
- Check: `scripts/test_coordinator_readonly_boundaries.py` passes, and the independent preflight suite's byte-identical-project assertions still hold.

### 2026-10-04 — A dependent task cannot see its ancestors by waiting
- Cause: the first design ran each task as soon as its dependencies were `verified`, without moving any ancestor commit into its worktree. The dependent workflow hashed its declared inputs, the base version was still present, and it executed against the untouched base — a green run that proved nothing about the dependency. The failure is silent: no layer reports "the file was there, from the wrong commit".
- Response: verified ancestor commits are merged into the dependent worktree before its plan is read, in dependency order, and the merge refuses a conflict instead of guessing. The integration workflow must also declare every task output as one of its inputs, which is checked statically before any worktree exists, so its acceptance is a combined acceptance rather than a self-reported pass.
- Check: the real batch records `dependencies: ["left", "right"]` on the dependent task and a combined acceptance that found all three ancestor artifacts in the integrated tree; a contested path between two ancestors blocks the descendant with the conflict recorded.

### 2026-10-04 — A declared-label review has no signature to verify
- Cause: `reviewer_credentials.verify` requires the exact proof field set including `signature`, and a declared-label proof has none, so reusing that check for a coordinator publication reported every valid label decision as `invalid`. Verified mode was unaffected, which is why the credential path looked correct while the default path could never publish.
- Response: verified mode keeps the project's issuance authority — signature, registry epoch, revocation. Declared-label mode is verified as what it actually is: an intact recorded integrity digest bound to this exact artifact set, criteria, project and checkout, with no signature invented for it. The report names the method that produced the decision.
- Check: the real batch publishes through a declared-label decision, a revoked credential stops a verified-mode publication, and both cases name their method in the report.

### 2026-10-04 — Verify optional writes and the checker itself
- Cause: readiness initially allowed a report to overwrite project control metadata; a grader used writable mounts plus file modes and skipped checker fingerprints, letting a candidate chmod and replace the checker. Mutation followed by an expected exception also escaped the first input check.
- Response: independently freeze positive and negative boundaries. Restrict readiness reports to their own namespace and keep persisted receipts consistent; require a real read-only container mount and input checks on error paths before accepting the study grader. Readiness corrections pass; grader corrections remain under independent review.
- Lesson: successful reference outputs prove functionality, while adversarial controls establish whether the verification can be trusted. Neither substitutes for the other.

### 2026-10-04 — Keep clocks and provider smoke tests explicit
- Cause: a readiness producer test wrote current evidence then checked it against an older fixed clock; actual Python 3.9 correctly reported future evidence. A legacy CLI smoke test unexpectedly launched two failed provider generations.
- Response: use the same current aware clock for the current-evidence fixture without changing future/stale rejection tests. Retain both provider failures outside the controlled study; mock collectors in CLI tests and start live study calls only after freezing its verified protocol. No study generation has been performed yet.

- 2026-10-04 | Native integration acceptance exposed editable root OpenCode configuration, editable broker native configuration trees, malformed Codex inline TOML, and delivery reported before injection. Frozen independent cases reject each; repair under implementation review. Repository scripts suite also exceeded its unchanged 60-second gate; measuring actual slow cases before selecting a fix.

- 2026-10-04 | Gate timing: measured 661 script cases; slowest 2.695 seconds, aggregate exceeds existing 60-second directory timeout. Retain all discovered cases and the 60-second invocation limit through bounded sequential suites, with nonzero failure/timeout propagation. Implementation and final gate proof pending.

### 2026-10-05 — Synthetic callback shapes hid native failures
- Root cause: native CLI output contained unsupported metadata; OpenCode message identity is optional on input, Codex tool fields differ from internal API fields, and successful OpenCode help is written to stderr.
- Approved solution: supported wire-only receipts, real output-message identity with conflict checks, native tool normalization and post-edit invalidation, and successful help across both streams. Freeze independent failures and verify production consumers.
- Status: wire delivery and same-batch recovery verified; final positive edit and OpenCode production pilots pending.

### 2026-10-05 — pipx backend compatibility
- Cause: local pipx selected an installed uv 0.5.9 while requiring uv>=0.9.17, refusing installation before environment setup.
- Solution: use `pipx install --backend pip --editable .` in the bound toolkit checkout; installation and external-directory CLI discovery pass without upgrading unrelated tools.

### 2026-10-05 — OpenCode never received injected context
- السبب الجذري: plugin hook reassigned `output.system` instead of mutating the host-owned array; hook ran, model saw nothing (proved with a scratch plugin: push delivers, assign does not).
- الحل المعتمد: push in place and refuse a missing/non-array `system`; regression test `scripts/test_opencode_system_inplace.py`.
- الحالة: محلول (2026-10-05)

### 2026-10-05 — Selected-map context scored 0/11 in the frozen study
- السبب الجذري: verified 2026-10-05 from stored artifacts — helper bodies WERE present; all 8 selected-map modules used relative imports (`from .money import`) and hit ImportError on 11/11 cases, all full-source modules used `from src.money import`. The map prompt showed no package import form.
- الحل المعتمد: none yet; do not claim savings. A follow-up needs a map that carries required bodies, preregistered as a new protocol.
- الحالة: مفتوح

### 2026-10-05 — A foreign project was committed to main
- السبب الجذري: commits ran from a nested wrong Git parent, `main` had no protection and the validator accepted unknown top-level projects.
- الحل المعتمد: separate private repository, main protection (PRs, strict required checks, conversation resolution, admins enforced) and the mandatory scope gate in `scripts/check_repository.py`.
- الحالة: محلول (2026-10-05); historical commits remain in public history

### 2026-10-06 — Selected-map quality collapse resolved by the v2 arm
- السبب الجذري: the v1 map never showed the package import form; verified 2026-10-05.
- الحل المعتمد: dependency-closure map plus offline sufficiency gate; v2 run scored 99/99 on all 18 trials, same as full-source.
- الحالة: محلول (2026-10-06); the ceiling means harder tasks are needed to separate the arms

### 2026-10-06 — OpenCode generations refused for an invented response shape
- السبب الجذري: verified from stored outputs — `opencode run` has no schema flag and nothing stated the shape; 13 flat path→source maps and 1 `{"files":…}`.
- الحل المعتمد: `opencode_schema_instruction` in the agent system prompt (`scripts/model_host.py`); an earlier append-to-prompt design broke the frozen "prompt exactly once" test and was dropped.
- الحالة: محلول في الكود (2026-10-06); real-model confirmation and the 4 ~300 s timeouts remain open

### 2026-10-09 — Catalog and dashboard boundaries
- Cause: project-local bindings did not provide a checked cross-project list; independent auth module copies could lose the process session list, and mobile grid min-content could overflow the viewport.
- Fix: explicit catalog with disjoint canonical roots, shared process session state, and zero-minimum mobile grid tracks.
- Check: redirected/moved identity, nested roots, concurrent registration and selected cancellation regressions; actual browser verification. Account-wide dollar limits and cross-provider quality remain unverified.

### 2026-10-09 — Login friction on a local dashboard
- Cause: the launcher required a generated access secret even on loopback.
- Fix: explicit password-free local mode with URL/Origin guards; never inherited for remote binds.
- Check: launcher and authorization regressions plus cookie-free browser/API smoke.

- 2026-10-09: Independent host environment could misrepresent a wildcard listener. Centralized npm launch and verify server.address() before local access; direct Next startup fails closed.

### 2026-10-10 — Scheduling, shared admission and measured activity
- Shared ceilings were previously per-checkout and queue startup could collide with active project reservations. Added locked shared admission, priority queue, identity/intent revalidation and queued waiting_for state. Unknown or failed billing retains allowances. Claude has no local login; OpenCode advertised the configured model but generation still exited 1 after explicit-model diagnostic; provider evaluation remains incomplete.

### 2026-10-11 — Operational features do not establish better user understanding
- Cause: Coordination and passing synthetic acceptance checks do not measure whether an agent understood the owner.
- Solution: Add source-linked statements and labelled interpretations to existing context; retain corrections and block explicitly unresolved questions.
- State: Mechanism tested; automatic ambiguity detection and controlled real-task quality measurement remain open.

- 2026-10-11 compatibility: Python 3.9 CI rejected the new hardlink test fixture because `Path.hardlink_to` is newer. Use `os.link` in the fixture; the runtime hardlink guard is unchanged.

- 2026-10-11 review: Native lifecycle serialization initially omitted selected user context, and frozen/history copies inherited permissive file modes. Include the block as mandatory native payload and reuse the existing atomic owner-only writer for current, archived and invalidated contexts; 14 regressions pass.

### 2026-10-11 — Ignore rules alone cannot protect publication
- Cause: Tracked files bypass ignores; conversation sources and installed role memory previously remained addable. Normal and temporary indexes may differ from the working files.
- Fix: Private source snapshots/registrations, role-memory ignores, chained index-object guard and explicit export selection. Batched object scanning avoids per-file subprocess overhead.
- Boundary: Existing uploaded history and unknown secrets require separate review; private edits to tracked public code must be separated into local input/override data rather than hidden with Git flags.
- 2026-10-11 | Ignored role memory vanished in new coordinator worktrees, blocking model execution | Initialize independent local memory from public templates while preserving guides/existing lessons; root private lessons are not copied. Regression uses a private root marker.
- 2026-10-11 | Git worktrees inherit core.hooksPath | Resolve the committing worktree, verify common Git directory and bound project identity, scan its own index and run prior hooks there; root source registrations remain protected.
- 2026-10-11 | Absolute hooksPath became stale after relocation, and last-line ignore detection duplicated effective rules | Validate/re-home the owned guard during rebind; only later negations trigger ignore repair.

- 2026-10-11 | Next dependency retained PostCSS 8.4.31 with known source-map file-disclosure advisories | Pin patched 8.5.29 without a Next major upgrade; known-violation regression, all dashboard tests/build and clean audit verify compatibility.

- 2026-10-11 | Replacing shared hooksPath from each linked worktree could chain owned guards into a cycle | Validate common Git directory/project/wrapper ownership, reuse the inherited guard and retain worktree-local source registrations.

- 2026-10-11 | Memory plumbing alone cannot prove better understanding | Prepare paired synthetic correction/scope/assumption/ambiguity cases using the actual production selector and a held-out strict grader. Requested publication is classified separately from real execution permission; no benchmark safety shortcut grants authority.

- 2026-10-11 | One latest-record stream let operator hypotheses hide user quotes; known regressions failed with supersedes=1 and selected IDs=[2] | Separate revision/selection streams by kind, preserve both in actual payloads, and retain source checks. Pretrial rubric audit also separates publication request from permission and asks for missing language only when the task requires it.

- 2026-10-11 | A classification benchmark can blame a model for evidence missing from its prompt | Audit independently required source IDs and exact scope/quotes before calls; reproduced missing quote and foreign project are rejected. This checks input coverage, not semantic model quality.

- 2026-10-11 | Authenticated CLI login did not establish successful bounded generation: first two actual calls exited 1. Preserved the failed study, stopped identical failures, and started separate private transport diagnostics rather than replacing attempts.

- 2026-10-11 | Cached desktop model gpt-6.1-sol was rejected by actual CLI ChatGPT transport; a separately identified gpt-5.5 diagnostic succeeds. Model availability must be proven by transport rather than inferred from cache/login.

- 2026-10-11 | Live paired understanding study observed a valid but wrong raw-history Arabic latest-correction response: language became unknown and clarification was requested despite explicit newer English preference. Preserve trial; compare paired selected-context result before changing prompts or rubric.

- 2026-10-11 | One selected-context English publication-classification response requested unnecessary clarification; preserve the failing trial and audit request/grading semantics before changing the benchmark.

- 2026-10-11 | Audited remaining selected-context failure: deployment_environment requested during publication classification, although execution was explicitly excluded. Keep baseline score and target current-action clarification in the next separately identified evaluation.

- 2026-10-11 | Generated planning repeatedly validated normalized tuple dependencies through list-only helper and failed 13 checks. Generation saw helper prose but omitted actual helper implementations; add source closure without leaking acceptance tools or modifying baseline evidence.

- 2026-10-11 | Feedback repair fixed normalized-input revalidation; two remaining failures exposed closed-cycle ambiguity and hidden twice error substring. Clarify cycle contract and validate exception type rather than wording; independent regression rejects wrong exception type.

- 2026-10-11 | Five report acceptance failures included undisclosed exact translation/message requirements. Publish exact title copy as model input and grade error semantics rather than undocumented phrases; keep numerical/immutability/CLI checks unchanged.

- 2026-10-11 | Integration checker retained an undocumented unknown report input fields phrase after per-task report grading was corrected. Check offending key while retaining exit2/no-output assertions; regression rejects missing key and independent actual-byte verification passes.

- 2026-10-11 | Manual failure explanations lived outside the workflow evidence chain. Add project-scoped repair references and hash-validated immutable candidate copies; avoid rewriting original attempts or granting log text execution authority.

- 2026-10-11 | Appending feedback after the base-prompt check could exceed its budget, and a mutable Docker tag could change repair acceptance. Check the complete prompt before provider calls, pin the recorded verifier image digest and test both refusals. Ordinary runtime .crewloom inputs are reserved; use a separately guarded ignored repair namespace for candidate copies.

- 2026-10-11 | Final repair budget guard counts all model repair requests by original workflow across new IDs and branches. Regression rejects a branch after two requests, an oversized feedback prompt before provider calls and a substituted verifier image. Final Docker workflow31 passes.

- 2026-10-11 | Repository gate rejected three new fixture Git subprocesses without explicit environments. Added repo_map.git_environment() to each; the in-flight commit was stopped before publication so the corrected files can be staged and pass a fresh mandatory hook. No hook bypass used.

- 2026-10-11 | The actual commit hook then exposed ambient GIT_INDEX_FILE reaching privacy.check from a new temporary workflow fixture. Scrub Git exports for the entire fixture lifetime as well as each Git subprocess; production foreign-index refusal remains intact. Reproduce with an explicit foreign index environment before retrying the full hook.

- 2026-10-11 | Review found missing grader fingerprint and subset-only prompt audit; add grader to frozen inputs and require exact record sequences. Regressions reproduce both invalid conditions. Earlier trial report cannot retroactively prove a grader mutation check it did not run.

- 2026-10-11 | Task-scoped OpenCode config intentionally excludes global custom provider definitions. Add an explicit private endpoint/model/byte-budget contract without importing plugins or wider host settings. A real installed-CLI protocol fixture verifies routing; catalogue presence alone did not establish cloud generation availability.

- 2026-10-11 | Final merge audit found an overbroad DOTALL conflict-marker expression had omitted owned appended memory. Restore full ef25e9e memory and retain both reviewed-main and local-profile additions; assert original lines remain before regenerating the manifest. Code changes were unaffected. Narrowed real OpenCode cloud diagnostic also returned FreeTierError; preserve both transport failures and stop repeats.

- 2026-10-11 | Bounded/single-link did not establish provider file confidentiality. Enforce current-user ownership and owner-only POSIX modes instead of silently accepting typical022-umask files; preserve native ACL limitations.

- 2026-10-12 | Local OpenCode provider setup was mistaken for a restriction of all Crewloom improvement features. Separate supported automatic model adapters from portable external-agent task contracts; keep review, context freshness and command verification independent of agent brand. External reply import and automatic repair require a reviewed adapter, not an unsupported host label.

- 2026-10-12 | PR18 P2 identified a late ordinary-editor mutation after the second prompt read. Move an additional source/binding/context check after that read; project locks only serialize Crewloom callers. Regression mutates an input immediately before the final builder returns and requires refusal.

- 2026-10-12 | Review reproduced page-controlled numeric index spoofing and unguarded/fake API status in old branch. Fix by retaining element references, validating generations/visibility, gating controls in persistent Chrome state and reusing current-main route guards. Success badges and Accessibility claims replaced by unknown. Missing local Node dependencies initially blocked an existing CSS test; npm ci restored the pinned dependencies and all46 tests pass.

- 2026-10-12 | Mandatory hook caught new browser/native-plugin assets missing from the distribution contract. Update explicit public asset patterns and sdist includes, retain Node-only dashboard exclusion, and add native/plugin resource coverage; all18 packaging regressions pass. No gate bypass.

- 2026-10-12 | Direct helper convenience defaults must not become runtime message defaults: CLICK_INDEX now requires an integer generation before dispatch. A real Chrome transport request without it is rejected, while current-generation requests pass.

- 2026-10-13 | PR19 review found password values exposed by index fallback and first-open capture lost before listeners existed. Replace value fallback with form labels and queue window/tab-bound requests; reject missing/sentinel capture windows.

### 2026-10-14 — Defect root causes and fixes
- Cause: mutable tab identity in callbacks; generation collisions across documents; first400 DOM order; own-element-only interactivity; template/heading-based readiness; whitespace argument splitting.
- Fix: request/tab/frame/document-bound replies, action fingerprints and hit tests; viewport/frame/shadow inventory with pagination; run-based status and compact-record parsing; bounded quote/JSON argument data and CLI-only external-root tools.
- Evidence: bad cases reject old behavior, current regressions pass. Browser tests need arrow-function predicates under extension CSP; a bare expression triggered unsafe-eval and was corrected without weakening CSP. ZIP freshness now has bad/clean acceptance and rejects undeclared source files.

### 2026-10-14 — External candidate freshness and MCP schemas
- Cause: exporting a packet alone left candidate publication to host-specific code; output edits could be overwritten while generation was in progress.
- Solution: compare project/task/context/input/prompt/output revisions, recheck staged original bytes, reuse transactional publication, retain private replies and require existing review/verification. Tests reject foreign/stale packets, undeclared outputs, links and owner edits before/after staging.
- SDK lesson: current official SDK uses MCPServer and Python3.11+; dict[str, Any] exposes direct structured results, while typing.Dict wrapped output. Current Playwright click schema requires target, not the older ref argument. Use actual list-tools schemas and live calls.

### 2026-10-14 — Local package manager backend
- Cause: pipx's default uv backend rejected an older installed uv before changing the Crewloom environment.
- Solution: use the supported pip backend for the same editable immutable snapshot and pinned MCP extra, then verify the installed module source, actual stdio tools, dashboard source and downloadable ZIP. Preserve the previous snapshot for rollback.

### 2026-10-14 — Parsed JSON is not a typed run
- Cause: the first malformed-row fix excluded null/scalars but cast objects after checking only tool/exit/root. An object-valued source/duration could still reach React, and invalid dates could count toward role health.
- Solution: validate every Run field at the parsing boundary and skip only the bad row. Reject wrong types, nonfinite/negative durations and invalid dates; use realistic timestamped log fixtures. Known violation rejected before the change;56-test clean suite and TypeScript pass.

### 2026-10-14 — Clarification and native scope boundaries
- Cause: source-linked context needed explicit recording; preserving questions without blocking native tools could still allow an edit. Fix: task opt-in, literal-source capture, unanswered-question guard and later-message exact answers; disabling capture preserves history. Ordinals survive canonical JSON key sorting.
- Native lesson: short project-private sockets are required by macOS; refuse long paths, autostart and broad-daemon fallback. CuaDriver bounded startup requires actual human manifest approval; prepare and test before requesting it. Driver schemas and TCC readiness need live acceptance.
- Evaluation: a cached/configured model ID was rejected by the actual authenticated CLI. Retain the two transport failures and blocked trials, then record an explicitly different available model in a separate run. Requested IDs are not verified backend identity.

- 2026-10-15 | Cause: bounded app scope denies global list_apps, while get_window_state indexes only actionable rows and appends unrelated menu history. Solution: bind observed PID, rely on bounded driver bundle validation, filter exact window ancestry and retain only window text for static state. Real counter acceptance passed without widening the reviewed manifest.

- 2026-10-15 | Real paired Ledgerline execution exposed package-relative imports under a top-level CLI, and root user context absent from task worktrees. Clarify runtime imports without changing verifiers; freeze selected source-linked context into each task checkout. GitHub Python3.9 found eager asyncio.Lock construction outside an event loop; initialize it lazily in async actions.

- 2026-10-16 | Independent QA found raw tax rates just outside0..100 admitted after quantization; added two refusal cases reject old fixture/candidate, clarified pre-rounding validation and regenerated only affected delivery work. Repair templates now declare criteria for immutable feedback. An atomic CLI writer cannot replace a preallocated Docker output mount: stage inside container tmp and stream to the declared artifact; preserve the failed attempt.

- 2026-10-16 | PR20 review found child-frame overlays surviving clear/failure, equal quota wasting dense-page capacity, and advertised cross-origin targets rejected on click. Track contacted frames before replies, allocate the remaining budget, and omit embedding paths whose visibility cannot be verified. Four regressions reject the prior source and pass the correction.

- 2026-10-16 | Release gate correctly rejected the stale test requiring development-only metadata. Updated the release metadata check to require0.6.0 and its matching changelog entry; the normal full gate must pass before commit.

- 2026-10-17 | Arabic panel logs wrapped English known errors and the page HUD ignored the saved language; empty capture/accessibility labels also stayed English. Reuse the panel dictionary and structured HUD messages, preserve unknown diagnostics, and update only the owned HUD. New rendered tests also exposed display:flex!important overriding the hide action; explicit important inline display preserves hiding across language changes.

- 2026-10-17 | PR22 review reproduced an untranslated internal capture-disable race. Paired delayed-capture regression rejects the prior candidate in Arabic and accepts the fix without rendering captured data. Audit/map the remaining literal internal guards; a persistent contract check now requires both language resources for every literal companion error, while preserving external diagnostics.
