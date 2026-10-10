# Repository architecture

[Public architecture](../documentation/ARCHITECTURE.md) describes the toolkit boundaries. [AGENTS.md](../AGENTS.md) is the single authority for agent behavior. Public role procedures and core tools improve in their existing paths; do not maintain duplicate versioned implementations.

Model generation passes explicit project text to a trusted CLI in a temporary directory; the artifact layer validates writes and the Docker executor verifies code. Host CLI flags are not an OS sandbox. Trial treatment labels remain outside the deterministic scorer.

Managed runs use tool-free provider RPC and declared-file container snapshots. Native CLI use requires an explicit operator exception. The trusted runtime cannot be a managed output destination.

### 2026-10-04 — Concurrent worktree coordination with reviewed integration
- The task coordinator is one layer over the existing managed executor, not a second runtime: each task runs `workflow.run` inside its own Git worktree, so isolation, the declared-artifact broker, the attempt ledger and the image policy stay shared with an ordinary workflow. Batch ownership is a kernel-held advisory lock, and the root is held with the same reservation a managed workflow writes, so ordinary workflow and native-context writers refuse it in both directions. The project lock covers short controller state and Git mutations only; each worktree takes its own root lock while it runs.
- A task commit carries only its verified declared outputs, so combining task commits once carries artifact diffs. Verified ancestor commits are merged into a dependent worktree before it runs, so it reads its ancestors' files rather than the untouched base. A failed or blocked task blocks its dependents with the blocking IDs recorded; no partial acceptance exists.
- The root moves only through one recorded `--ff-only` fast-forward of a reviewed candidate, after the manifest, project and checkout binding, every task commit, output hashes, criteria, integration head, recomputed diff digest, reviewer credential and revocation, current root HEAD, clean tracked tree and untracked collisions have all been revalidated. The nonce of a consumed decision cannot be replayed. Conflicts keep every branch, worktree and index; nothing is reset, forced or cleaned, and no push or GitHub merge exists.
- Not claimed: this is not a scheduler, a provider client, or a boundary for arbitrary host tools; a command step is the only step kind it runs; reclaiming batch ownership does not stop a container that outlived its controller; a declared-label review names a reviewer without authenticating one, and a credential proves key possession only; Git's own atomicity limits still apply to that single fast-forward.

### 2026-10-03 — Recoverable grouped artifact publication
- One declared output group is published as one recoverable transaction: the whole group, its destinations and its input fingerprints are validated before the first write; the group and a backup of every destination it replaces are staged under protected `.crewloom` with a scoped journal; the project lock is held for the whole publication and its recovery. A failure is rolled back to the recorded content and mode, or removes only files that attempt created, and only after every journal record is proven restorable, so a rollback never leaves an unrecorded third state.
- This is recoverable grouped publication, deliberately not an instant multi-file atomic filesystem change: a reader that ignores the project lock can observe a group half applied. Managed writers serialise on the same lock and an interrupted group converges instead of accumulating.
- Publication recovery runs before any managed work observes the project: project entry reconciles it after the identity/ownership preflight and before any criteria, instruction, context or reservation write, and a workflow run reconciles it before it reads workflow state. A destination that no longer matches its journal is refused and left untouched with its journal kept for manual review.
- The root lock is reclaimed only for an owner that is provably gone, under an exclusive reclamation claim and verified against the exact inode the record was read from. Reclamation never follows a symlinked lock, claim or owner path and never deletes unrecognised claim contents; an unrecognised claim blocks the root for manual reconciliation. Reclaiming a lock does not stop a command or container that outlived its process.

### 2026-10-02 — Context efficiency
- Model prompts select whole historical records with Unicode lexical relevance and bounded budgets; constitution, architecture, roadmap and inputs remain full. Reuse validates prompt hashes; history is not rewritten.

### 2026-10-02 — Repository navigation
- Project maps use Python AST and approximate JS/TS extraction with per-root SHA-keyed parsing cache. Map metadata is opt-in for managed prompts and never substitutes for actual declared source inputs.

### 2026-10-02 — Automatic project context
- Project identity is split into a portable `crewloom.project.json` project ID and a local `.crewloom/binding.json` checkout ID; navigation and context caches are rebuildable, lessons and task records are durable. Every generation is scoped to project ID, checkout ID, canonical root and task ID, and a stable semantic fingerprint excludes telemetry so unchanged entry reuses its generation. Lifecycle shares the workflow root lock and its reservation discipline in both directions; managed runner entry, checkpoint, publication gate and finalization reuse the existing broker, ledger and provider restrictions. Lesson promotion requires recorded executor evidence, never prose.

### 2026-10-09 — Machine-local project catalog
The existing project binding module owns catalog registration, overlap guards and setup. Portable config and checkout binding remain the identity sources; the catalog stores local references only. Dashboard monitoring reads explicit entries through the CLI; cancellation resolves project roots server-side and uses the existing project lock. Existing role/tool panels retain their selected execution root.

### 2026-10-09 — Password-free local dashboard
The launcher explicitly enables loopback-only local access. Local URLs and exact local mutation Origins are checked before project access; non-loopback deployments retain configured-token authentication. No generated token or cookie is required locally.

- 2026-10-09: Password-free local access now reads the real HTTP listener address/port from the npm custom server; an environment flag alone fails closed.

### 2026-10-10 — Scheduling, shared admission and measured activity
- An explicit machine-local queue schedules registered canonical roots by priority, with one active batch per root and unchanged coordinator worktree/review boundaries. The managed model step reserves shared request/dollar admission atomically before creating a provider attempt; unknown cost retains allowance. Dollar admission is not a vendor account billing cap.

### 2026-10-11 — Source-linked user understanding
The existing frozen context owns delivery of optional project-local user statements, labelled assumptions and explicit task interpretations. `user_context.py` records exact source quotes and hashes under the selected project/checkout, uses the existing lock and reservation protocol, retains correction history and fails on unresolved questions or stale sources. Provenance is not speaker authentication, factual truth, user confirmation or execution authority. No external memory runtime is required.
