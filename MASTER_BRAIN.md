# Crewloom shared memory

2026-10-06 review priority: close measured provider/context-quality failures, correct dashboard evidence semantics and reconcile the exact runtime/release identity before expanding role count or claiming savings. See [the version-scoped 32-item project review](documentation/PROJECT_REVIEW.md); this assessment changes no runtime or remote state.

2026-10-06 privacy implementation: project-local data stays ignored and is checked against the exact Git index; parallel model tasks receive independently writable same-project memory. Declarative source policy remains versioned. [Privacy contract](documentation/PROJECT_PRIVACY.md); 77 cases pass with real Docker, local integration pending.

[Architecture](Brain/ARCHITECTURE.md) · [Completed](Brain/COMPLETED.md) · [Challenges](Brain/CHALLENGES.md) · [Ideas](Brain/IDEAS_VAULT.md) · [Backlog](Brain/ROADMAP_TODO.md)

The current toolkit tree keeps project-specific operational state outside shared role memory. Earlier commits include a project-scope incident; see [the scope guide](documentation/REPOSITORY_SCOPE.md). See [the constitution](AGENTS.md) for the memory lifecycle and [the release notes](documentation/RELEASE.md) for validation scope.

Public edition 0.2.0 restores detailed references and ships twelve catalogued local tools, with six runnable examples.

Project runtime root is separate from library code; CLI/dashboard histories and installed role memory are project-local. See documentation/PROJECTS.md for scope and evidence.

Crewloom 0.4.0 adds Docker-isolated software commands, project-bound state and task handoffs, six detailed English software contracts, readiness and host-layout setup, and an objective feature scorer. Supplied-fixture execution is validated; real provider superiority and authenticated independent review are not claimed.

Crewloom 0.5.0 adds bounded Codex/Claude artifact-generation adapters, an executed Codex-to-Docker feature example, a reproducible provider-trial coordinator, and English specialist procedures for all 42 roles. Ten Codex submissions tie at 9/9 on one contract; Claude authentication blocks cross-host results. No general superiority or authenticated independent-review claim.

The owner-selected maintenance workflow name is Self-Editing Mode / التعديل الذاتي. It uses the existing skill-improvement-engineer role and task permissions; activation and acceptance are documented in documentation/SELF_EDITING.md.

Managed enforcement is implemented through declared-file snapshots and tool-free provider RPC. Repository instructions alone cannot bind unmanaged host agents. See [the trust boundary](documentation/ENFORCEMENT.md).

Context efficiency selects reusable project lessons without rewriting history or claiming model training. Measured byte reduction and limits are documented in [context efficiency](documentation/CONTEXT_EFFICIENCY.md).

Project-local repository navigation now supplements memory selection; maps are advisory and managed provider metadata inclusion is explicit. See [repository maps](documentation/REPOSITORY_MAP.md).

Automatic project context is now implemented for opted-in projects: portable project identity, a local checkout binding, versioned navigation generations scoped by `source_roots`, frozen per-task context with hash-validated code ranges, and lessons that only recorded executor evidence can promote. Lifecycle labels distinguish managed runner, instruction-assisted and manual operation; opening a folder never triggers anything by itself. Optional read ranges carry their own byte allowance and record cap instead of filling the global context ceiling, and a completed model step re-verifies against the exact frozen generation it consumed. See [project context](documentation/PROJECT_CONTEXT.md) and [the plan it implements](documentation/AUTOMATIC_PROJECT_CONTEXT_PLAN.md). Live provider token, cost and answer-quality effects remain unmeasured, and no new tagged release is asserted. Two public English/Arabic navigation and lifecycle pilots passed the fixed acceptance contract; [their evidence](examples/evaluation/project-context-20261003/README.md) distinguishes bytes from provider billing.

Concurrent workflow scope uses explicit project roots, process locks and paused-task reservations. Different roots run in parallel; same-root task ownership persists until completion or explicit cancellation. Direct host tools are outside these guards.

Crewloom `0.6.0.dev0` adds an installable wheel and sdist built from one explicit resource resolver, so discovery, validation, context packs, project context and workflows work outside the source checkout without duplicating the role tree. It requires dashboard authentication on every API read, write and the event stream, delivers the generated secret and issued reviewer credentials to owner-only files instead of standard output, and adds optional credential-verified reviewers whose signed, scoped, revocable proofs derive from an issuance authority held in protected `.crewloom` runtime state. This is development metadata, not a tag: see [release notes](documentation/RELEASE.md). Dashboard session revocation is per process and the reviewer registry is an owner integrity boundary, not an OS sandbox; credential possession still does not prove a distinct human reviewed the work. Phases B and C remain required.

### 2026-10-03 — Automatic project context implementation published
Project-local identity, incremental maps, frozen context and executor-verified lessons are implemented and uploaded in PR #2. Public English/Arabic navigation pilots each pass nine frozen checks; provider billing and general answer-quality gains remain unmeasured. Managed lifecycle refresh is automatic; native operation is instruction-assisted and private-client adoption awaits registry reconciliation.

### 2026-10-03 — Automatic-context core plan complete
PR #2 is merged into public main as `d9e6c64` after all hosted checks pass on `13b29e4`. Managed lifecycle, public frozen pilot evidence and project isolation are delivered; private-client rollout, provider billing/quality studies and native host callbacks remain separate extensions.

### 2026-10-04 — Concurrent worktree coordination with reviewed integration
A project-local manifest DAG now runs as a real batch: one Git worktree per task under the project's `.crewloom`, up to four concurrent managed executors using the same isolation, declared-artifact broker, failure ledger and image policy as any workflow, and verified ancestor commits merged into a dependent worktree before it runs. Only verified declared outputs are committed, generated instruction context and user files never are. Batch ownership is a kernel-held advisory lock and the root is held with the same reservation an ordinary workflow writes, so managed and native writers refuse it in both directions. The checked-out tree changes only when an explicit reviewed decision, revalidated against the manifest, binding, every task commit, output hashes, criteria, integration head, diff digest, credential and revocation, root HEAD, tracked cleanliness and untracked collisions, moves it by one recorded `--ff-only` fast-forward; a consumed decision cannot be replayed, and worktrees are retained afterwards as the evidence they are bound to. Real Docker evidence covers two overlapping workers, a dependent task reading integrated ancestors, a combined acceptance over the integrated tree, and a published candidate equal to the reviewed head. This is concurrency with reviewed integration, not a scheduler, a provider client, or a boundary for arbitrary host tools; no model produced any of the evidenced artifacts. See [the coordinator](documentation/COORDINATOR.md).

### 2026-10-03 — Recoverable grouped publication and safe lock reclamation
One declared output group now publishes as one recoverable transaction under the project lock: the whole group, its destinations and its input fingerprints are validated before the first write, the group and a backup of every replaced destination are staged under protected `.crewloom` with a scoped journal, and a rollback happens only after every journal record is proven restorable. An interrupted group is reconciled before project entry writes anything and before a workflow run reads state, freezes context, evaluates a gate or records acceptance; a third-party edit blocks reconciliation and keeps its journal. Committed and reverted groups both leave a bounded receipt, so failed attempts stay as history rather than pending residue. Root-lock reclamation no longer follows symlinked claim, owner or lock paths and never recursively deletes claim contents; an unrecognised claim blocks the root for manual reconciliation. The navigation index's real JS/TS grammars moved behind one optional `crewloom[syntax]` extra with exact pins, and `js_syntax` is packaged as a flat runtime module. This is recoverable grouped publication, deliberately not an instant multi-file atomic filesystem change, and reclaiming a lock still does not stop a command or container that outlived its process. The concurrent worktree coordinator, native host adapters, the live usage/quality/latency study and rollout readiness remain required. See [enforcement](documentation/ENFORCEMENT.md) and [execution](documentation/EXECUTION.md).

### 2026-10-04 — Production foundation verification in progress
Crewloom keeps Apache-2.0 and English public foundation documents, with Arabic operation. Independent checks now cover installed resources, authentication, review credentials, real syntax navigation, recoverable publication, scoped readiness and native transport accounting. Concurrent AI workflows, native lifecycle completion and live context savings remain acceptance work; current synthetic references and historical navigation byte reductions do not establish model superiority or billed savings.

### 2026-10-05 — Production verification checkpoint
Crewloom now has independently verified concurrent app execution and same-batch permission recovery, plus actual Codex context delivery and Docker acceptance. Native payload parsing and supported-host production checks are being completed before measuring 36 controlled trials and publishing the integrated source. Installation and offline callback tests remain distinct from actual host operation.

### 2026-10-05 — Project isolation is enforced, not promised
A foreign application reached `main` once. The toolkit now carries a mandatory scope contract checked at commit time, in CI and from installed copies, and `main` requires pull requests with strict checks. The first frozen context study did not show a token saving: the selected map scored 0/11 on every scored Codex trial. Do not claim savings until a redesigned arm passes.

### 2026-10-06 — Closure map keeps quality on the first v2 run
After fixing the cause of the v1 failure (missing import form), the closure-map arm matched full-source on every held-out check with about 18% fewer input tokens on three synthetic tasks (one host). It is a measured input-token reduction with no quality loss observed, not a cost or speed result; the tasks are at the ceiling, so do not claim a quality or billing advantage.
### 2026-10-05 — Public entrypoint reviewed
English/Arabic setup, project-root selection and actual study limitations are aligned. Brand assets share the existing palette and a dedicated mobile layout; supplied commands and 12 current-source previews pass. The first map study still does not establish useful token savings.

### 2026-10-06 — Repeated source-scoped audit
Published 40d4168a now contains the completed first v2 study: 18 scored Codex trials, 99/99 held-out checks in each arm and 18.3867% fewer mean input tokens for closure-map on three synthetic tasks. Cost and speed savings remain unestablished. Local privacy/brand work is still separate from published main. Release acceptance additionally needs all-depth source-archive private exclusions and staged-ignore readiness, both newly reproduced with synthetic fixtures; the passing build/install and hosted suites do not cover those cases.

### 2026-10-06 — Intelligence product direction
The detailed design prioritizes trustworthy publication and sufficient fresh context, then evidence-driven lesson reuse and verified delivery. Four further retrieval/lesson counterexamples are recorded; adding roles or critic calls cannot substitute for fixing them. Proposed multi-project UX and provider-aware optimizations remain measured, scoped acceptance work; no automatic pooling of client memory or unreviewed runtime upgrades.

### 2026-10-06 — Owner operating requirements added to plan
Crewloom remains separate from supplied application roots. Planned durable project checkpoints let work continue from Claude to another authorized host after quota interruption, with preserved attempts/budgets and source/ownership verification. Effective model/host capability profiles restrict execution to observed capability and selected policy; completion claims still require actual evidence. Automatic handoff is opt-in, and these requirements are not runtime implementation claims.

### 2026-10-06 — Unified Crewloom implementation plan
INTELLIGENCE_ROADMAP.md now holds the sole active plan:12 work packages covering39 review items and separate-root, quota-continuation and capability contracts. README and project backlog point to it; earlier reviews/designs remain evidence/history. Consolidation does not mark implementation or release acceptance complete.

### 2026-10-06 — Next-stage product decision
Prioritize trusted publication and correct context before automatic routing or broader orchestration. New local fixes improve private-state/staged-ignore handling, but independent archive and index fixtures still expose incomplete boundaries despite passing existing suites. The unified plan now compares reusable external mechanisms and defines practical acceptance/benefit measures. Manual cross-host continuity follows verified effective capabilities; no universal token-saving or hallucination-free claim, runtime repair or public release is established by this review.

### 2026-10-06 — Implementation report reconciled with evidence
Independent follow-up confirms20 packaging cases on compatible setuptools80.10.2 and5 existing root-guard cases. The report's broader R33/R34 completion claims conflict with unchanged-source negative controls, so the unified register/memory now describe partial repair. Preserve the original attempt report/checkpoint and reconcile its status before continuation. No source repair, full-gate revalidation or publication is claimed by this assessment.

### 2026-10-06 — Reusable-tool product discussion
Owner proposes Crewloom tools following a shared contract/clean-code/reuse standard and confirmed toolkit-only scope. Candidate architecture builds on the existing catalog: reusable logic, thin interfaces, explicit project-bound contracts and verified promotion. Discover only needed metadata to reduce repeated context work, then measure the benefit. Consumer code/scripts are outside scope; no implementation or token-saving guarantee is established by this discussion.

### 2026-10-07 — PR8 repair guarantees
Verified with real validation, real processes and a real Docker daemon: one owner wins a simultaneous handoff and a loser cannot dispatch or publish; no side effect precedes its required checkpoint; an aggregate output reservation cannot be over-allocated; cancellation stops a whole process tree and removes only containers whose ID and label match. Not claimed: cost caps, caps on native CLI use, a real cross-host handoff, universal isolation, or W01–W12 completion. New tools follow N04: one catalog, lifecycle, evidence bound to source, an incremental gate.

### 2026-10-07 — Repaired-head guarantees remain scoped
Independent review confirms135 targeted passes,45 preserved frozen files and9 successful CI checks at e77dbeb, including real Docker ownership. N04 still has staged-view/classification and acceptance/dependency-provenance gaps; actual Python3.9 can promote zero tests, and unavailable process observation can lose live-resource tracking. Preserve current source-scoped handoffs and repair these existing W03/W09 deltas before stronger enforcement/release claims. No runtime repair, host pilot or merge is established by this review.

Existing recorded-plan/OpenCode-bound review observations also reproduce; four unresolved conversations under required resolution are a concrete merge condition despite green CI. Default plan validation and effective host bounds stay in W04/W03. This assessment did not resolve threads, reply externally or change branch protection.

### 2026-10-07 — Remaining PR8 defects repaired within stated bounds
The tool gate now judges the staged or committed snapshot, rejects unguarded and disguised operational code, requires a contract or exact-bytes exception for changed legacy tools, and binds verification to implementation, imports, contract, acceptance bytes and structured counts; empty acceptance cannot promote on Python 3.9 or 3.14. Process-inspection failure preserves tracking; checkpoints are validated against their recorded plan; OpenCode preflight uses its argv bound. Still not claimed: coverage of dynamic imports/test helpers, the 15 legacy tools, Windows process identity, cost caps, a real cross-host handoff or universal enforcement.
