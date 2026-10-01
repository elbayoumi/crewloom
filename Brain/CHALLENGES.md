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

### 2026-10-01 — Paused tasks released process ownership
- Cause: Process locks ended on manual-task handoff, permitting a different workflow to start in that root; implicit cwd also allowed ambiguous selection.
- Fix: Require explicit task root and persist a project-bound active-workflow reservation; only matching continuation/cancellation may take over.
- Check: Concurrent same/different-root, paused-task, cancellation and redirected reservation regressions. Direct host edits remain outside runner protection.
