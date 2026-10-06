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

### 2026-10-05 — Public documentation and brand assets
The entrypoint uses a wide and mobile SVG banner plus a separate square loom mark under assets/. The existing ink/mint/blue palette stays authoritative in documentation/BRANDING.md. Inventory counts belong in verified README text; native lifecycle and map quality claims link to recorded evidence.

### 2026-10-06 — Local data and index privacy
Project runtime/snapshots/backups stay in ignored .crewloom; installed consumer role memory and local host controls are ignored at setup. Portable declarative policy remains trackable source. Bootstrap/install refuse reserved or ignored tracked index entries using cleared Git environments and exact roots; the toolkit gate repeats that check. Consumer CI/hooks can invoke the read-only project privacy command. Model task worktrees seed separate private memory copies from the same selected project and preserve resume state; source guides are frozen Git inputs. Public templates are distinguished by the actual toolkit root or its genuine linked Git repository, never a caller-supplied project ID.

### 2026-10-06 — Archive and staged-policy audit boundaries
Source archives need private-namespace exclusions at every depth; root-only prunes do not constrain nested inputs under approved public directories. Local working-tree ignore coverage is distinct from the staged policy that would be committed. Keep these separate from index classification, content-secret scanning and OS isolation, and verify actual extracted artifacts with synthetic private canaries.

### 2026-10-06 — Intelligence design proposal
INTELLIGENCE_ROADMAP.md proposes in-place upgrades to map/context, conditional lessons, existing workflow/coordinator and dashboard. Trust and sufficiency correctness precede ranking/automation; tool-free managed providers retain controller-owned retrieval and bounded declared scope. This is a design, not a runtime architecture change.

### 2026-10-06 — Continuation and capability requirements (planned)
The intelligence roadmap now requires independent application/toolkit roots, controller-owned project checkpoints for cross-agent quota continuation, and effective host/model capability profiles. Handoffs preserve identity, dirty edits, acceptance/failure evidence, budgets and single-writer ownership; receivers revalidate source and capabilities. Manual continuation precedes explicit opt-in automation. These are design contracts, not shipped runtime behavior.

### 2026-10-06 — One active implementation plan
documentation/INTELLIGENCE_ROADMAP.md is the unified plan and sole W01–W12 execution register, covering R01–R39 and N01–N03. Reviews, older context plans and backlog snapshots preserve evidence/history; their prior delivery orders are superseded. This reorganizes planning, not runtime architecture.

### 2026-10-06 — Next-stage acceptance boundaries
W01/W02 must validate reviewed build inputs, all-depth reserved namespaces, symlink targets and final wheel/sdist metadata/content; a late sdist filter is insufficient. Staged privacy evaluates portable rules separately from local exclusions and must refuse unmerged policy while checking the relevant nested scope. W03 separates CLI launch support from observed effective capabilities; W04 reconciles interrupted operations at owned durable boundaries. Detailed decisions and benefit criteria remain in the unified plan; this review implements no runtime change.

### 2026-10-06 — Implementation-report acceptance
A controller checkpoint must distinguish implemented changes, tested cases and closed requirements. Passing a narrow suite with the pinned backend does not invalidate wider source-matched counterexamples. Reconcile contradictory completed/pending records and unknown/failure lists before dispatch; retain prior evidence instead of silently turning an implementation report into acceptance.

### 2026-10-06 — Tool architecture discussion
Candidate direction: extend the existing machine catalog with versioned contracts, reusable toolkit cores and thin interfaces using current project-bound executor controls. Owner confirmed Crewloom tools only; consumer code/scripts are outside scope and toolkit helper modules need not become public tools. The proposal is recorded in IDEAS_VAULT; no SDK, schema enforcement, migration or execution boundary is implemented by this discussion.
