# Crewloom shared memory

- 2026-10-15: Repository review retains the prior defect-closure work and adds explicit-prerequisite refusal, real MCP/browser CI, lockfile dashboard startup, reviewed dependency proposals and synchronized bilingual setup. Local component acceptance passes; source proposal/hosted CI and stable-release rollout are distinct. See [review evidence](documentation/PROFESSIONAL_REVIEW.md).

[Architecture](Brain/ARCHITECTURE.md) · [Completed](Brain/COMPLETED.md) · [Challenges](Brain/CHALLENGES.md) · [Ideas](Brain/IDEAS_VAULT.md) · [Backlog](Brain/ROADMAP_TODO.md)

The public edition contains clean role memory and shared repository memory. It has no imported customer or agency execution history. See [the constitution](AGENTS.md) for the memory lifecycle and [the release notes](documentation/RELEASE.md) for validation scope.

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

### 2026-10-09 — Explicit project management
Crewloom now has a machine-local disjoint-root catalog, memory-preserving setup and authenticated multi-project task monitoring. Existing managed coordinator and execution budgets are reused. Live model comparisons and provider-account spending caps remain separate, explicitly unverified work.

### 2026-10-09 — Dashboard usability
Local Crewloom dashboard opens directly without passwords. Remote hosting remains a separate authenticated configuration; local guards do not sandbox arbitrary host processes.

### 2026-10-10 — Scheduled project batches and shared admission
Crewloom now has an explicit-catalog priority queue, shared managed-generation admission, bounded project-local role charts and honest cost status. Project reservations and reviewed publication remain authoritative. Synthetic bilingual developer evidence includes three successful Codex trials and preserved transport failures; broad provider/role quality and vendor billing caps are not demonstrated.

### 2026-10-11 — Quality direction
Crewloom now supports optional source-linked user context inside existing frozen generations. Statements retain quotes; interpretations remain labelled, and project/user selection is explicit. This addresses context provenance rather than claiming stronger model intelligence. Next quality milestone: controlled bilingual misunderstanding/correction measurements.

- Review verification: Selected understanding is mandatory in native Codex/Claude/OpenCode payload serialization as well as managed prompts; frozen copies use owner-only atomic writes. Serializer tests are not a live-provider quality benchmark.

### 2026-10-11 — Private by storage, deliberate by publication
User sources and customization data stay project-local; commit hooks reject private index blobs and known credentials. Existing hooks are retained. Export prepares only explicitly selected files and never publishes automatically. This is a Git-path protection layer, not encryption or universal leakage prevention.

- 2026-10-11 | Privacy rollout also patches the dashboard CSS processor and verifies an actual outside-file read refusal; known dependency advisories are tested independently from Git data publication controls.

- 2026-10-11 | Parallel task privacy setup reuses verified inherited protection while preserving checkout-local source registrations; independent task setup does not create recursive hook chains.

- 2026-10-11 | The next agency-quality gap is measured user understanding. Pinned Arabic/English contracts and strict corruption-tested grading are prepared; live provider evidence and general agency delivery strength are still unproven.

- 2026-10-11 | Understanding preparation exposed and repaired actual context loss across quoted/assumed memories. Production payloads retain both evidence kinds; fixture grading is prepared, while measured AI quality and full agency effectiveness remain open.

- 2026-10-11 | Understanding benchmark source-coverage audit added locally and regression-tested; live model measurement and practical agency delivery remain pending.

- 2026-10-11 | Understanding collection now runs locally, but the first live study yielded no scored responses because of CLI transport failure. Agency capability remains unverified beyond demonstrated runtime safeguards.

- 2026-10-11 | Actual understanding evidence now includes one raw-history correction mistake avoided by paired selected context, with the full frozen study still running. Practical agency delivery remains unproven.

- 2026-10-11 | Completed private understanding pilot shows 17/18 selected-context passes versus 14/18 raw-history on nine synthetic cases; PR #16 contains collection tooling. Practical agency delivery remains unproven.

- 2026-10-11 | Practical delivery remains pending; contract/grader mismatch repaired and live attempt retained separately. Understanding PR review fixes committed as 096f473 through full gate.

- 2026-10-11 | Generated multi-file example now passes separate real combined13/helper16 verification after acceptance contract alignment. Library changes still pending publication and original coordinator delivery has not been approved.

- 2026-10-11 | Initial explicit repair runtime is local and regression-tested; automated repair preparation/dispatch and practical delivery approval remain pending.

- 2026-10-11 | Crewloom now has local evidence-driven repair preparation/execution with unchanged acceptance and private candidate history. One real requested-model pilot passed five bilingual checks after a seeded failure; general model improvement and competitive performance remain unproven.

- 2026-10-11 | PR #16 review tightened grader/arm immutability; original pilot remains a limited observation. Practical repair improved planning but uncovered undocumented grader requirements, so agency acceptance remains pending.

- 2026-10-11 | Flexible OpenCode selection now supports private loopback provider contracts without merging global host configuration. Actual protocol compatibility is demonstrated; actual weak-model or Claude-level capability is not.

- 2026-10-12 | Crewloom improvement contracts now include portable task-packet export for external agents alongside five automatic model adapters. Export shares scoped context and evidence rules but grants no execution/acceptance authority; arbitrary automatic host dispatch remains unsupported.

- 2026-10-12 | Crewloom now packages a native Codex entry plugin alongside a manual browser companion. Current-main authorization, persistent default-off activation and reference-bound element checks address the reviewed local issues. Real browser/installed-plugin evidence establishes these integrations only; autonomous desktop/model control remains future scoped work.

- 2026-10-14 | Browser/dashboard13-defect closure implemented with rejected old cases and passing current tests: Python1123 (107skip), dashboard55, Docker77, real Chromium38 (1optional skip), distribution12. Manual browser control remains explicit; new MCP/desktop integration requires its own live evidence. Local runtime rollout follows the mandatory commit gate; no public merge or all-role performance claim.

- 2026-10-14 | Browser/dashboard13-defect fixes are committed behind the mandatory hook. Optional bound MCP and external candidate import now pass real stdio/Docker acceptance; isolated Playwright navigation/snapshot/click/close verified. Local runtime rollout pending final gate; native desktop and general model quality remain unverified.

- 2026-10-14 | Local13-defect closure delivered: gated commits, immutable CLI/dashboard snapshot, Chrome2.3.0 ZIP and read-only Codex MCP registration. Runtime HTTP, rendered English/Arabic and exact installed MCP command verified. Native desktop and cross-model/full-role quality remain explicit acceptance work.

- 2026-10-14 | Native prompt capture now opts in per task, preserves exact private sources and blocks project tools on source-linked heuristic questions. Actual MCP answer transport passes. Two requested usable models each scored selected4/4 versus raw2/4 on two bilingual synthetic scenarios; model identity was not independently reported. Fixture-scoped native AX tools are implemented and compiled, while human manifest approval and live Accessibility control remain pending.

- 2026-10-14 | Capture/clarification/native-client continuation is gated at ef7782a (99 suites,1207 tests with optional skips), installed locally and verified through all three actual read-only MCP tools. Native control remains unverified pending human manifest approval; synthetic quality evidence does not establish full agency delivery.

- 2026-10-15 | Approved fixture-scoped native control now has real observe/press/reobserve evidence (0→1→0), plus stale-handle and foreign-process refusal. Global-discovery and menu-projection defects repaired within the unchanged manifest. General desktop automation and broad role-quality claims remain unverified.

- 2026-10-15 | Native fixture correction is gated (99 suites/1211 tests with optional skips) and verified through the installed CLI. Approved test processes were closed after acceptance. No claim of general desktop control or full-role quality follows from this result.

- 2026-10-15 | Delivery continuation now exercises two independent model-generated Ledgerline projects. Actual failures exposed context delivery and import-contract gaps; their fixes preserve verifier bytes. PR20 is open; general app acceptance and final publication remain pending until verified.

- 2026-10-16 | 0.6.0 operational acceptance is recorded with complete real generated software delivery, independent container checks and post-delivery correction. Real profile/browser and two system-app scopes passed.42 role guides validate, with live evidence limited to named software/context/QA/MCP/machine workflows. Final normal GitHub merge/release and local refresh remain the delivery steps.

- 2026-10-17 | Arabic and English are paired product acceptance requirements for localized changes, with RTL/LTR and failure-state evidence. Language support scope is explicit; external diagnostics and application labels retain their source text.
