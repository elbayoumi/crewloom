# Crewloom shared memory

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

### 2026-10-03 — Automatic project context implementation published
Project-local identity, incremental maps, frozen context and executor-verified lessons are implemented and uploaded in PR #2. Public English/Arabic navigation pilots each pass nine frozen checks; provider billing and general answer-quality gains remain unmeasured. Managed lifecycle refresh is automatic; native operation is instruction-assisted and private-client adoption awaits registry reconciliation.

### 2026-10-03 — Automatic-context core plan complete
PR #2 is merged into public main as `d9e6c64` after all hosted checks pass on `13b29e4`. Managed lifecycle, public frozen pilot evidence and project isolation are delivered; private-client rollout, provider billing/quality studies and native host callbacks remain separate extensions.
